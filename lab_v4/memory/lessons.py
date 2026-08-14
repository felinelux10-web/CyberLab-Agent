# CyberLab Agent v4.0
# memory/lessons.py

from lab_v4.memory.db import Database

class Lessons:

    def __init__(self, db: Database):
        self.db = db

    def record(self, error_pattern: str, solution: str, success: bool):
        existing = self.db.fetchone(
            "SELECT * FROM lessons WHERE error_pattern=?",
            (error_pattern,)
        )
        if existing:
            self.db.execute(
                """UPDATE lessons
                   SET total_count = total_count + 1,
                       success_count = success_count + ?,
                       solution = ?
                   WHERE error_pattern = ?""",
                (1 if success else 0, solution, error_pattern)
            )
        else:
            self.db.execute(
                """INSERT INTO lessons
                   (error_pattern, solution, success_count, total_count, created_at)
                   VALUES (?, ?, ?, 1, ?)""",
                (error_pattern, solution, 1 if success else 0, self.db.now())
            )

    def find(self, error_pattern: str) -> dict | None:
        return self.db.fetchone(
            "SELECT * FROM lessons WHERE error_pattern=?",
            (error_pattern,)
        )

    def success_rate(self, error_pattern: str) -> float:
        lesson = self.find(error_pattern)
        if not lesson or lesson["total_count"] == 0:
            return 0.0
        return lesson["success_count"] / lesson["total_count"]

    def all_lessons(self) -> list:
        return self.db.fetchall(
            "SELECT * FROM lessons ORDER BY total_count DESC"
        )
