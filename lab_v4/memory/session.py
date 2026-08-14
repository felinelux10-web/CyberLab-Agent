# CyberLab Agent v4.0
# memory/session.py

from lab_v4.memory.db import Database

class Session:

    def __init__(self, db: Database):
        self.db = db
        self.session_id = None
        self.tasks_done = 0
        self.files_modified = 0
        self.error_count = 0

    def start(self) -> int:
        cursor = self.db.execute(
            """INSERT INTO sessions (started_at, tasks_done,
               files_modified, error_count)
               VALUES (?, 0, 0, 0)""",
            (self.db.now(),)
        )
        self.session_id = cursor.lastrowid
        return self.session_id

    def record_task(self):
        self.tasks_done += 1
        self._sync()

    def record_file_modified(self):
        self.files_modified += 1
        self._sync()

    def record_error(self):
        self.error_count += 1
        self._sync()

    def _sync(self):
        if not self.session_id:
            return
        self.db.execute(
            """UPDATE sessions
               SET tasks_done=?, files_modified=?, error_count=?
               WHERE id=?""",
            (self.tasks_done, self.files_modified,
             self.error_count, self.session_id)
        )

    def end(self) -> dict:
        summary = self.summary()
        self.db.execute(
            """UPDATE sessions
               SET ended_at=?, summary=?
               WHERE id=?""",
            (self.db.now(), str(summary), self.session_id)
        )
        return summary

    def summary(self) -> dict:
        return {
            "session_id"    : self.session_id,
            "tasks_done"    : self.tasks_done,
            "files_modified": self.files_modified,
            "error_count"   : self.error_count,
        }
