# CyberLab Agent v4.0
# core/agent.py

from lab_v4_dev.core.project_metadata import ProjectMetadata
from lab_v4_dev.core.config import HARD_LIMITS
from lab_v4_dev.core.state import AgentState
from lab_v4_dev.core.logger import log
from lab_v4_dev.memory.db import Database
from lab_v4_dev.memory.session import Session
from lab_v4_dev.memory.store import MemoryStore
from lab_v4_dev.monitor.health_check import check_health
from lab_v4_dev.loop.event_loop import EventLoop
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.core.contracts import Request, Response
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.dni.dni_core import DNICore



class Agent:

    def __init__(self):
        self.state   = None
        self.db      = None
        self.session = None
        self.loop    = None
        self.context = None
        self.runtime = None

    def boot(self) -> bool:
        log.info("=== CyberLab Agent v4.0 BOOTING ===")

        # 1. قراءة MASTER_REF
        try:
            self._meta = ProjectMetadata()
            self.ref   = self._meta.as_dict()
            log.info(f"MASTER_REF loaded — version {self._meta.get_version()}")
        except Exception as e:
            log.critical(f"MASTER_REF failed: {e}")
            return False

        # 2. تهيئة State
        self.state = AgentState()
        self.state.load()
        log.info(f"State: {self.state.mode}")

        # 3. تهيئة DB
        self.db = Database()
        self.db.connect()
        if not self.db.integrity_check():
            log.critical("DB integrity check failed")
            self.state.enter_frozen_mode("db_corruption")
            return False
        log.info("DB: OK")

        # P07 — canonical Memory ownership
        self.memory = MemoryStore(self.db)

        # 4. health check
        health = check_health(self.state)
        if not health["healthy"]:
            log.warning(f"Health issues: {health}")
        else:
            log.info("Health: OK")

        # 5. تهيئة Session
        # P07 — MemoryStore owns the semantic Session component.
        self.session = self.memory.session
        self.memory.start_session()

        # 6. تهيئة Loop و Context
        self.executor = None
        self.loop    = EventLoop(self.state, self.db, self.session, self.memory)
        self.context = ContextStore()
        self.orchestrator = Orchestrator(self, context=self.context)

        self.dni = DNICore()

        # Conversation Layer (H.8.5)
        from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
        from lab_v4_dev.conversation.conversation_manager import ConversationManager
        self.dialogue_memory = DialogueMemory(self.context)
        self.dni.attach_dialogue_memory(self.dialogue_memory)
        self.conv_manager    = ConversationManager(self.orchestrator, self.dialogue_memory, self.dni)

        # 6.1 تهيئة Runtime Session (Series 9)
        try:
            from lab_v4_dev.runtime.runtime_integration import get_runtime
            self.runtime = get_runtime()
            self.runtime.start(
                operation="boot",
                project="cyberlab_agent",
                goal="agent_boot",
                phase="initialization"
            )
            self.runtime.monitor_check()
        except Exception as _re:
            log.warning(f"Runtime init skipped: {_re}")
            self.runtime = None


        # 7. Auto Context Restore (v4.8)
        try:
            from lab_v4_dev.memory.session_state import load_session
            from lab_v4_dev.data.project_timeline import init_timeline
            init_timeline()
            s = load_session()
            if s and s.get("active_goal"):
                print(f"\n[v4.8] جلسة سابقة موجودة:")
                print(f"  الهدف   : {s.get('active_goal','?')}")
                print(f"  الخطوة  : {s.get('next_step','?')}")
                print(f"  اكتب 'استكمل الجلسة' للاسترجاع أو تجاهل الرسالة للبدء من جديد")
        except:
            pass

        log.info("=== AGENT READY ===")
        return True

    def run(self, user_input: str) -> dict:
        request = Request.from_input(user_input)

        if not self.loop:
            return {"status": "error", "reason": "agent not booted"}

        if self.state.mode == "frozen":
            return {"status": "frozen", "reason": "manual intervention required"}

        # Conversation Layer هو المسار الرئيسي (H.8.5)
        result = self.conv_manager.process(request.raw_text)

        if result.get("status") == "unsupported":
            return result

        if result.get("status") == "success":
            self.session.record_task()

        return result


    def reset_conversation_context(self):
        """
        P06 — Canonical conversational lifecycle boundary.

        ContextStore remains the canonical execution-context owner.
        DialogueMemory owns only DialogueState/history/reference state.
        NLU context remains an independent TTL-based NLU cache.
        """
        context = getattr(self, "context", None)

        if context is not None:
            # Reset only conversational execution state.
            for name in (
                "last_intent",
                "last_target",
                "last_result",
                "current_subject",
                "current_version",
                "current_file",
                "current_analysis",
            ):
                if hasattr(context, name):
                    setattr(context, name, None)

            history = getattr(context, "history", None)
            if hasattr(history, "clear"):
                history.clear()

        memory = getattr(self, "dialogue_memory", None)
        if memory is not None:
            reset = getattr(memory, "reset", None)
            if callable(reset):
                reset()

    def shutdown(self):
        if self.runtime:
            self.runtime.lifecycle.stop()
        log.info("=== SHUTTING DOWN ===")
        if self.session:
            summary = self.session.end()
            log.info(f"Session summary: {summary}")
        if self.state:
            self.state.save()
        if self.db:
            self.db.close()
        log.info("=== SHUTDOWN COMPLETE ===")
