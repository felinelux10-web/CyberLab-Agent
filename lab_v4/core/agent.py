# CyberLab Agent v4.0
# core/agent.py

import yaml
from lab_v4.core.config import HARD_LIMITS
from lab_v4.core.state import AgentState
from lab_v4.core.logger import log
from lab_v4.memory.db import Database
from lab_v4.memory.session import Session
from lab_v4.monitor.health_check import check_health
from lab_v4.loop.event_loop import EventLoop
from lab_v4.core.orchestrator import Orchestrator
from lab_v4.awareness.context_store import ContextStore

MASTER_REF_PATH = "lab_v4/configs/MASTER_REF.yaml"

class Agent:

    def __init__(self):
        self.state   = None
        self.db      = None
        self.session = None
        self.loop    = None
        self.context = None

    def boot(self) -> bool:
        log.info("=== CyberLab Agent v4.0 BOOTING ===")

        # 1. قراءة MASTER_REF
        try:
            with open(MASTER_REF_PATH) as f:
                self.ref = yaml.safe_load(f)
            log.info(f"MASTER_REF loaded — version {self.ref['project']['version']}")
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

        # 4. health check
        health = check_health(self.state)
        if not health["healthy"]:
            log.warning(f"Health issues: {health}")
        else:
            log.info("Health: OK")

        # 5. تهيئة Session
        self.session = Session(self.db)
        self.session.start()

        # 6. تهيئة Loop و Context
        self.executor = None
        self.loop    = EventLoop(self.state, self.db, self.session)
        self.orchestrator = Orchestrator(self)
        self.context = ContextStore(self.db)

        log.info("=== AGENT READY ===")
        return True

    def run(self, user_input: str) -> dict:
        if not self.loop:
            return {"status": "error", "reason": "agent not booted"}

        if self.state.mode == "frozen":
            return {"status": "frozen", "reason": "manual intervention required"}

        # Shadow Mode — لا يؤثر على النتيجة
        shadow = self.orchestrator.handle(user_input)
        log.debug(f'Orchestrator shadow: {shadow["status"]}')

        self.loop.submit(user_input)
        result = self.loop.tick()

        if result:
            if result["status"] == "done":
                self.session.record_task()
            elif result["status"] == "failed":
                self.session.record_error()

        return result or {"status": "idle"}

    def shutdown(self):
        log.info("=== SHUTTING DOWN ===")
        if self.session:
            summary = self.session.end()
            log.info(f"Session summary: {summary}")
        if self.state:
            self.state.save()
        if self.db:
            self.db.close()
        log.info("=== SHUTDOWN COMPLETE ===")
