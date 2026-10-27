# CyberLab Agent v4.0
# memory/task_history.py

from lab_v4_dev.memory.db import Database

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
        bounded_limit = max(1, min(100, int(limit)))
        return self.db.fetchall(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (bounded_limit,)
        )

    def search(self, query: str, limit: int = 10) -> list:
        from lab_v4_dev.memory.intelligence import rank_memory_records
        candidates = self.db.fetchall(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT 500"
        )
        return rank_memory_records(
            query, candidates, fields=("intent", "plan", "status"),
            minimum_score=0.18, limit=max(1, min(100, int(limit))),
        )

    def count_by_status(self):
        rows = self.db.fetchall(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        )
        return {r["status"]: r["count"] for r in rows}
