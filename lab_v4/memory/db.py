# CyberLab Agent v4.0
# memory/db.py

import sqlite3
import os
from datetime import datetime

DB_PATH = "lab_v4/memory/agent.db"
SCHEMA_PATH = "lab_v4/memory/schema.sql"

class Database:

    def __init__(self):
        self.conn = None

    def connect(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._apply_schema()

    def _apply_schema(self):
        with open(SCHEMA_PATH, "r") as f:
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

    def integrity_check(self):
        result = self.fetchone("PRAGMA integrity_check")
        return result and list(result.values())[0] == "ok"
