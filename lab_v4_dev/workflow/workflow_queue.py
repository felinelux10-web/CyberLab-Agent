"""
Series 7 — Workflow Queue

المسؤولية:
- إدارة طابور المهام.
"""

from collections import deque


class WorkflowQueue:

    def __init__(self):
        self._queue = deque()

    def enqueue(self, task):
        self._queue.append(task)
        return {"status": "queued", "size": len(self._queue)}

    def dequeue(self):
        if not self._queue:
            return None
        return self._queue.popleft()

    def peek(self):
        if not self._queue:
            return None
        return self._queue[0]

    def size(self):
        return len(self._queue)

    def is_empty(self):
        return len(self._queue) == 0

    def clear(self):
        self._queue.clear()
        return {"status": "cleared"}
