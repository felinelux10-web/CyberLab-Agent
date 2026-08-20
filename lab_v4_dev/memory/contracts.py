"""
P07 — Memory Contracts

Narrow semantic contracts for the Memory layer.

These contracts intentionally do not implement persistence.
Existing SQLite/JSON implementations remain untouched until
their actual call graph is verified in the next P07 batch.
"""

from typing import Protocol, Any


class SessionMemory(Protocol):
    def start(self) -> int:
        ...

    def record_task(self) -> None:
        ...

    def record_file_modified(self) -> None:
        ...

    def record_error(self) -> None:
        ...

    def end(self) -> dict:
        ...

    def summary(self) -> dict:
        ...


class TaskMemory(Protocol):
    def add(self, intent: str, plan: str = None) -> int:
        ...

    def update_status(self, task_id: int, status: str) -> None:
        ...

    def get(self, task_id: int):
        ...

    def recent(self, limit: int = 10) -> list:
        ...

    def count_by_status(self) -> dict:
        ...


class LessonMemory(Protocol):
    def record(
        self,
        error_pattern: str,
        solution: str,
        success: bool,
    ):
        ...

    def find(self, error_pattern: str):
        ...

    def success_rate(self, error_pattern: str) -> float:
        ...

    def all_lessons(self) -> list:
        ...


class MemoryStore(Protocol):
    """
    High-level boundary for future Memory routing.

    Implementations are intentionally deferred until the
    existing call graph has been verified.
    """

    session: SessionMemory
    tasks: TaskMemory
    lessons: LessonMemory
