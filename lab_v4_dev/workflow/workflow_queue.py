"""P013 canonical workflow task queue."""

from collections import deque


class WorkflowQueue:
    """Owns queued workflow tasks only.

    Queue operations must not perform execution or mutate task lifecycle
    state. State transitions remain owned by WorkflowTask/WorkflowState.
    """

    def __init__(self):
        self._queue = deque()

    def enqueue(self, task: dict) -> dict:
        if not isinstance(task, dict):
            raise TypeError("task must be a dict")

        if "id" not in task:
            raise ValueError("task must contain id")

        self._queue.append(task)

        return {
            "status": "queued",
            "task_id": task["id"],
            "size": len(self._queue),
        }

    def dequeue(self) -> dict | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def peek(self) -> dict | None:
        if not self._queue:
            return None
        return self._queue[0]

    def contains(self, task_id: str) -> bool:
        return any(task.get("id") == task_id for task in self._queue)

    def size(self) -> int:
        return len(self._queue)

    def is_empty(self) -> bool:
        return not self._queue

    def clear(self) -> int:
        count = len(self._queue)
        self._queue.clear()
        return count
