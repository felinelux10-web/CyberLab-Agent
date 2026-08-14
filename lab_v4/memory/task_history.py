# CyberLab Agent v4.0
# memory/task_history.py

from lab_v4.memory.db import Database

class TaskHistory:

    def __init__(self, db: Database):
        self.db = db

    def add(self, intent: str, plan: str = None) -> int:
        cursor = self.db.execute(
            """INSERT INTO tasks (intent, plan, status, created_at, updated_at)
               VALUES (?, ?, 'pending', ?, ?)""",
            (intent, plan, self.db.now(), self.db.now())
        )
        return cursor.lastrowid

    def update_status(self, task_id: int, status: str):
        self.db.execute(
            """UPDATE tasks SET status=?, updated_at=?
               WHERE id=?""",
            (status, self.db.now(), task_id)
        )

    def get(self, task_id: int):
        return self.db.fetchone(
            "SELECT * FROM tasks WHERE id=?",
            (task_id,)
        )

    def recent(self, limit: int = 10):
        return self.db.fetchall(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )

    def count_by_status(self):
        rows = self.db.fetchall(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        )
        return {r["status"]: r["count"] for r in rows}
