"""
P07 — Memory Ownership Facade.

MemoryStore is the canonical owner-facing boundary for:
    - session memory
    - task history
    - lessons

It does not own:
    - conversation context
    - NLU context
    - runtime state
    - project knowledge
    - orchestration
    - routing
"""

from .db import Database
from .session import Session
from .task_history import TaskHistory
from .lessons import Lessons


class MemoryStore:
    """Canonical semantic owner of the Memory subsystem."""

    def __init__(self, db: Database):
        if db is None:
            raise ValueError("MemoryStore requires a Database instance")

        self.db = db
        self.session = Session(db)
        self.tasks = TaskHistory(db)
        self.lessons = Lessons(db)

    def _record_event(self, event_type: str, payload: dict | None = None) -> bool:
        try:
            self.db.record_event("session_task_lesson", event_type, payload or {})
            return True
        except Exception:
            # The event journal is observability, not a prerequisite for work.
            return False

    def start_session(self):
        session_id = self.session.start()
        self._record_event("session_started", {"session_id": session_id})
        return session_id

    def record_task(self):
        result = self.session.record_task()
        self._record_event("task_count_incremented")
        return result

    def record_file_modified(self):
        result = self.session.record_file_modified()
        self._record_event("file_change_count_incremented")
        return result

    def record_error(self):
        result = self.session.record_error()
        self._record_event("error_count_incremented")
        return result

    def end_session(self):
        summary = self.session.end()
        self._record_event("session_ended", {"session_id": self.session.session_id})
        return summary

    def session_summary(self):
        return self.session.summary()

    def add_task(self, intent: str, plan: str = None):
        task_id = self.tasks.add(intent, plan)
        self._record_event("task_created", {"task_id": task_id})
        return task_id

    def update_task_status(self, task_id: int, status: str):
        result = self.tasks.update_status(task_id, status)
        self._record_event("task_status_changed", {
            "task_id": int(task_id), "status": str(status),
        })
        return result

    def get_task(self, task_id: int):
        return self.tasks.get(task_id)

    def recent_tasks(self, limit: int = 10):
        return self.tasks.recent(limit)

    def search_tasks(self, query: str, limit: int = 10):
        return self.tasks.search(query, limit)

    def recent_memory_events(self, limit: int = 20):
        try:
            return self.db.recent_events(limit, owner="session_task_lesson")
        except Exception:
            return []

    def task_status_counts(self):
        return self.tasks.count_by_status()

    def record_lesson(
        self,
        error_pattern: str,
        solution: str,
        success: bool,
    ):
        result = self.lessons.record(error_pattern, solution, success)
        self._record_event("lesson_updated", {"success": bool(success)})
        return result

    def find_lesson(self, error_pattern: str):
        return self.lessons.find(error_pattern)

    def lesson_success_rate(self, error_pattern: str):
        return self.lessons.success_rate(error_pattern)

    def all_lessons(self):
        return self.lessons.all_lessons()
