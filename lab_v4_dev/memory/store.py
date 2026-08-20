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

    def start_session(self):
        return self.session.start()

    def record_task(self):
        return self.session.record_task()

    def record_file_modified(self):
        return self.session.record_file_modified()

    def record_error(self):
        return self.session.record_error()

    def end_session(self):
        return self.session.end()

    def session_summary(self):
        return self.session.summary()

    def add_task(self, intent: str, plan: str = None):
        return self.tasks.add(intent, plan)

    def update_task_status(self, task_id: int, status: str):
        return self.tasks.update_status(task_id, status)

    def get_task(self, task_id: int):
        return self.tasks.get(task_id)

    def recent_tasks(self, limit: int = 10):
        return self.tasks.recent(limit)

    def task_status_counts(self):
        return self.tasks.count_by_status()

    def record_lesson(
        self,
        error_pattern: str,
        solution: str,
        success: bool,
    ):
        return self.lessons.record(
            error_pattern,
            solution,
            success,
        )

    def find_lesson(self, error_pattern: str):
        return self.lessons.find(error_pattern)

    def lesson_success_rate(self, error_pattern: str):
        return self.lessons.success_rate(error_pattern)

    def all_lessons(self):
        return self.lessons.all_lessons()
