# CyberLab Agent v4.0
# core/agent.py

from lab_v4_dev.core.project_metadata import ProjectMetadata
from lab_v4_dev.core.config import HARD_LIMITS
from lab_v4_dev.core.state import AgentState
from lab_v4_dev.core.logger import log
from lab_v4_dev.core.boot_ui import BootUI
from lab_v4_dev.memory.db import Database
from lab_v4_dev.memory.session import Session
from lab_v4_dev.memory.store import MemoryStore
from lab_v4_dev.monitor.health_check import check_health
from lab_v4_dev.loop.event_loop import EventLoop
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.core.contracts import Request, Response
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.dni.dni_core import DNICore


_RECOVERABLE_EXECUTION_INTENTS = {
    "modify_code", "modify_file", "modify_function", "modify_class",
    "replace_body", "add_function", "add_class", "remove_function",
    "remove_class", "create_file", "delete_file", "move_file", "rename_file",
    "refactor_file", "refactor_project", "cleanup_code", "optimize_code",
    "upgrade_code", "run", "run_project", "run_file", "run_tests",
    "test_project", "test_file", "test_function", "generate_test",
    "generate_code", "analyze_code", "repair_approve", "repair_reject",
    "session_save",
}



class Agent:

    def __init__(self):
        self.state   = None
        self.db      = None
        self.session = None
        self.loop    = None
        self.context = None
        self.runtime = None
        self._pending_session = None

    def boot(self) -> bool:
        self._boot_ui = BootUI()
        self._boot_ui.start()
        self._boot_ui.row("BOOT", "Initializing startup checks", "INFO")

        # 1. قراءة MASTER_REF
        try:
            self._meta = ProjectMetadata()
            self.ref   = self._meta.as_dict()
            self._boot_ui.row("CONFIG", f"MASTER_REF v{self._meta.get_version()}")
        except Exception as e:
            self._boot_ui.row("CONFIG", f"MASTER_REF failed: {e}", "FAIL")
            log.critical(f"MASTER_REF failed: {e}")
            return False

        # 2. تهيئة State
        self.state = AgentState()
        self.state.load()
        self._boot_ui.row("STATE", f"Mode: {self.state.mode}")

        # 3. تهيئة DB
        self.db = Database()
        self.db.connect()
        if not self.db.integrity_check():
            self._boot_ui.row("DATABASE", "Integrity check failed", "FAIL")
            log.critical("DB integrity check failed")
            self.state.enter_frozen_mode("db_corruption")
            return False
        self._boot_ui.row("DATABASE", "Connection and integrity OK")

        # P07 — canonical Memory ownership
        self.memory = MemoryStore(self.db)

        # 4. health check
        health = check_health(self.state)
        if not health["healthy"]:
            self._boot_ui.row("HEALTH", "Review warnings in startup log", "WARN")
            log.warning(f"Health issues: {health}")
        else:
            self._boot_ui.row("HEALTH", "System checks passed")

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
        self._boot_ui.row("CORE", "Memory, session, context and dialogue ready")

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
            self._boot_ui.row("RUNTIME", "Monitoring initialized")
        except Exception as _re:
            self._boot_ui.row("RUNTIME", "Optional monitoring unavailable", "WARN")
            log.warning(f"Runtime init skipped: {_re}")
            self.runtime = None


        # 7. Auto Context Restore (v4.8)
        self._pending_work_sessions = []
        try:
            from lab_v4_dev.memory.session_state import (
                load_session, recoverable_work_checkpoint, get_session_index,
                get_recent_sessions, get_session_by_id, analyze_session,
            )
            from lab_v4_dev.data.project_timeline import init_timeline
            init_timeline()
            s = load_session()
            self._pending_session = s if isinstance(s, dict) else None

            # A new process starts a new live dialogue. A saved dialogue is
            # never injected implicitly; it must be selected explicitly so
            # "this session" and "a saved session" cannot be mixed.
            # Keep startup readable: show only the three most recently saved
            # sessions. Full details remain available through `session N`.
            all_sessions = get_session_index()
            # Session numbers follow the stable index order; recency is a
            # separate display concern. Do not derive a session number from
            # the position in a transient "recent sessions" list.
            number_by_id = {
                str(item.get("session_id") or ""): number
                for number, item in enumerate(all_sessions, 1)
                if str(item.get("session_id") or "").strip()
            }
            index = get_recent_sessions()
            if not index and isinstance(s, dict) and s.get("session_id", s.get("active_goal")):
                index = [s]
            if index:
                self._boot_ui.section("SAVED SESSIONS")
                self._boot_ui.row("SESSIONS", f"{len(index)} saved session(s)", "INFO")
                self._pending_work_sessions = []
                for item in index:
                    number = number_by_id.get(
                        str(item.get("session_id") or ""),
                        len(all_sessions) + 1,
                    )
                    selected = get_session_by_id(item.get("session_id")) or item
                    report = analyze_session(selected)
                    recoverable = recoverable_work_checkpoint(selected)
                    description = str(report.get("topic") or report.get("active_goal") or "جلسة بلا عنوان").strip()
                    description = description.splitlines()[0].strip()
                    if len(description) > 54:
                        description = description[:51].rstrip() + "…"
                    self._pending_work_sessions.append({
                        "number": number,
                        "report": report,
                        "recoverable": bool(recoverable),
                        "session_id": selected.get("session_id") or item.get("session_id"),
                        "session_type": str(selected.get("session_type") or item.get("session_type") or "work").casefold(),
                    })
                    session_type = self._pending_work_sessions[-1]["session_type"]
                    state_label = (
                        "DIALOGUE SAVED" if session_type == "dialogue"
                        else "RESUMABLE" if recoverable
                        else "REVIEW ONLY"
                    )
                    marker_state = "OK" if session_type == "dialogue" or recoverable else "WARN"
                    # The summary text itself remains Arabic/localized, while
                    # the surrounding startup labels stay in the default UI
                    # language and every session gets its own visual card.
                    self._boot_ui.session_card(
                        number, f"{description}  — {state_label}", marker_state
                    )
                visible_numbers = ", ".join(
                    f"session {item['number']}" for item in self._pending_work_sessions
                )
                self._boot_ui.row("DETAILS", f"Type {visible_numbers} for details", "INFO")
                self._boot_ui.close_section()
        except Exception as exc:
            log.warning(f"Session discovery skipped: {exc}")

        self._boot_ui.ready()
        return True

    def show_pending_session(self, command: str) -> bool:
        """Display full details only when the user selects a saved session."""
        import re

        match = re.fullmatch(r"\s*session\s+(\d+)\s*", command, re.IGNORECASE)
        if not match:
            return False
        number = int(match.group(1))
        sessions = getattr(self, "_pending_work_sessions", [])
        selected = next((item for item in sessions if item["number"] == number), None)
        if selected is None:
            print("لا توجد جلسة محفوظة بهذا الرقم.")
            return True

        report = selected["report"]
        detail_ui = BootUI()
        detail_ui.detail_card(
            f"تفاصيل الجلسة {number}: {report.get('topic') or report.get('active_goal') or 'جلسة بلا عنوان'}",
            [
                ("المعرّف", report.get("session_id", "غير متاح")),
                ("الهدف", report.get("active_goal", "غير محدد")),
                ("الحالة", f"{report.get('status', 'غير محددة')} — {report.get('last_updated', 'غير متاح')}"),
                ("آخر خطوة مكتملة", report.get("last_completed_step", "غير محدد")),
                ("نقطة التوقف", report.get("current_state", "غير محددة")),
                ("الخطوة التالية", report.get("next_step", "غير محدد")),
            ],
        )
        if selected["recoverable"]:
            print("الاستئناف يتطلب أمرًا صريحًا؛ لن يبدأ التنفيذ تلقائيًا.")
        else:
            print("هذه الجلسة للمراجعة فقط وليست قابلة للاستئناف التنفيذي.")
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
            self._save_dialogue_checkpoint()

        if result.get("status") == "success" and result.get("executed") is True:
            self.session.record_task()

        if (
            result.get("status") == "success"
            and str(getattr(result.get("intent"), "value", result.get("intent")))
            in _RECOVERABLE_EXECUTION_INTENTS
        ):
            self._save_recoverable_checkpoint()

        return result

    def _save_dialogue_checkpoint(self) -> None:
        """Persist conversational history separately from executable work state."""
        try:
            from lab_v4_dev.memory.session_state import save_dialogue_checkpoint
            from lab_v4_dev.core.project_context import get_active_project_root
            dialogue = self.dialogue_memory.snapshot() if self.dialogue_memory else None
            version = self._meta.get_version() if getattr(self, "_meta", None) else "unknown"
            save_dialogue_checkpoint(
                dialogue_state=dialogue,
                version=version,
                project_root=get_active_project_root(),
            )
        except Exception as exc:
            log.debug(f"Dialogue checkpoint skipped: {exc}")

    def _save_recoverable_checkpoint(self) -> None:
        """Persist only the recoverable work checkpoint after successful execution."""
        try:
            from lab_v4_dev.memory.session_state import save_recoverable_checkpoint
            from lab_v4_dev.core.project_context import get_active_project_root
            context = self.context.get_last() if self.context else None
            topic = (context or {}).get("subject") or (context or {}).get("current_subject")
            version = self._meta.get_version() if getattr(self, "_meta", None) else "unknown"
            current_file = (context or {}).get("file") or (context or {}).get("current_file")
            save_recoverable_checkpoint(
                active_goal=topic or "عمل جاري",
                next_step=(f"استكمال: {topic}" if topic else "استكمال الجلسة"),
                last_files=[current_file] if current_file else [],
                version=version,
                context_state=context,
                project_root=get_active_project_root(),
            )
        except Exception as exc:
            log.debug(f"Recoverable checkpoint skipped: {exc}")

    def restore_session_context(self) -> bool:
        """Restore only the explicit bounded checkpoint, never implicit history."""
        try:
            from lab_v4_dev.memory.session_state import load_session
            return self.restore_session_snapshot(load_session())
        except Exception as exc:
            log.warning(f"Session context restore skipped: {exc}")
            return False

    def restore_session_snapshot(self, saved: dict | None) -> bool:
        """Restore the explicitly selected session, not merely the latest one."""
        try:
            saved = saved if isinstance(saved, dict) else {}
            restored = False
            session_type = str(saved.get("session_type") or "").casefold()
            dialogue_state = saved.get("dialogue_state")
            context_state = saved.get("context_state") or {}

            # Legacy mixed records are treated as work when execution state is
            # present. Never restore dialogue and execution context from one record.
            if not session_type:
                session_type = (
                    "dialogue"
                    if isinstance(dialogue_state, dict) and not context_state
                    else "work"
                )

            if session_type == "dialogue" and self.dialogue_memory:
                restored = self.dialogue_memory.restore_snapshot(dialogue_state)
            context_restored = False
            if session_type in {"work", "mixed"} and self.context and isinstance(context_state, dict):
                clear_restored = getattr(self.dialogue_memory, "clear_restored_session", None)
                if callable(clear_restored):
                    clear_restored()
                for name in (
                    "last_intent", "last_target", "last_result", "current_subject",
                    "current_version", "current_file", "current_analysis",
                ):
                    if name in context_state:
                        setattr(self.context, name, context_state[name])
                context_restored = bool(context_state)
            self._pending_session = saved
            return restored or context_restored
        except Exception as exc:
            log.warning(f"Session context restore skipped: {exc}")
            return False


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
