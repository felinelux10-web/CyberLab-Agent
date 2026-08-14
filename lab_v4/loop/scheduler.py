# CyberLab Agent v4.0
# loop/scheduler.py

from collections import deque

class Scheduler:

    def __init__(self):
        self.queue = deque()

    def add(self, task: dict):
        self.queue.append(task)

    def next(self) -> dict | None:
        if self.queue:
            return self.queue.popleft()
        return None

    def has_tasks(self) -> bool:
        return len(self.queue) > 0

    def size(self) -> int:
        return len(self.queue)

    def clear(self):
        self.queue.clear()
