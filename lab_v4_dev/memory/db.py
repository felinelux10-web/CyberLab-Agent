# CyberLab Agent v4.0
# memory/db.py

import sqlite3
import os
import json
from datetime import datetime

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(ROOT_DIR, "lab_v4_dev", "memory", "agent.db")
SCHEMA_PATH = os.path.join(ROOT_DIR, "lab_v4_dev", "memory", "schema.sql")

class Database:

    def __init__(self):
        self.conn = None

    def connect(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 10000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._apply_schema()

    def _apply_schema(self):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = f.read()
        self.conn.executescript(schema)
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute(self, sql, params=()):
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor

    def fetchone(self, sql, params=()):
        cursor = self.conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, sql, params=()):
        cursor = self.conn.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    def now(self):
        return datetime.now().isoformat()

    def record_event(self, owner: str, event_type: str, payload: dict | None = None,
                     *, source: str = "memory_store", limit: int = 2000) -> int:
        """Append a bounded, privacy-minimal memory lifecycle event."""
        if self.conn is None:
            raise RuntimeError("Database must be connected before recording events")
        safe_payload = payload if isinstance(payload, dict) else {}
        cursor = self.execute(
            """INSERT INTO memory_events (owner, event_type, source, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (str(owner), str(event_type), str(source),
             json.dumps(safe_payload, ensure_ascii=False), self.now()),
        )
        bounded_limit = max(100, min(10000, int(limit)))
        self.execute(
            """DELETE FROM memory_events
               WHERE id NOT IN (
                   SELECT id FROM memory_events ORDER BY id DESC LIMIT ?
               )""",
            (bounded_limit,),
        )
        return int(cursor.lastrowid)

    def recent_events(self, limit: int = 20, *, owner: str | None = None) -> list:
        bounded_limit = max(1, min(200, int(limit)))
        if owner:
            return self.fetchall(
                """SELECT * FROM memory_events WHERE owner=?
                   ORDER BY id DESC LIMIT ?""",
                (str(owner), bounded_limit),
            )
        return self.fetchall(
            "SELECT * FROM memory_events ORDER BY id DESC LIMIT ?",
            (bounded_limit,),
        )

    def integrity_check(self):
        result = self.fetchone("PRAGMA integrity_check")
        return result and list(result.values())[0] == "ok"
