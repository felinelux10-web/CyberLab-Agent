# CyberLab Agent v4.0
# monitor/budget.py

from lab_v4_dev.core.config import HARD_LIMITS

class Budget:

    def __init__(self):
        self.tasks_this_hour = 0
        self.file_edits_this_session = 0
        self.consecutive_failures = 0

    def can_run_task(self) -> dict:
        if self.tasks_this_hour >= HARD_LIMITS["max_tasks_per_hour"]:
            return {"ok": False, "reason": "hourly task limit reached"}
        return {"ok": True}

    def can_edit_file(self) -> dict:
        if self.file_edits_this_session >= HARD_LIMITS["max_file_edits_per_session"]:
            return {"ok": False, "reason": "session file edit limit reached"}
        return {"ok": True}

    def record_task(self):
        self.tasks_this_hour += 1

    def record_file_edit(self):
        self.file_edits_this_session += 1

    def record_failure(self):
        self.consecutive_failures += 1

    def record_success(self):
        self.consecutive_failures = 0

    def is_critical(self) -> bool:
        return self.consecutive_failures >= HARD_LIMITS["max_consecutive_failures"]

    def reset_hourly(self):
        self.tasks_this_hour = 0

    def reset_session(self):
        self.file_edits_this_session = 0
        self.consecutive_failures = 0

    def status(self) -> dict:
        return {
            "tasks_this_hour"        : self.tasks_this_hour,
            "file_edits_this_session": self.file_edits_this_session,
            "consecutive_failures"   : self.consecutive_failures,
            "is_critical"            : self.is_critical(),
        }
