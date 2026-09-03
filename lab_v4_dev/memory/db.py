# CyberLab Agent v4.0
# memory/db.py

import sqlite3
import os
from datetime import datetime

DB_PATH = "lab_v4_dev/memory/agent.db"
SCHEMA_PATH = "lab_v4_dev/memory/schema.sql"

class Database:

    def __init__(self):
        self.conn = None

    def connect(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._apply_schema()

    def _apply_schema(self):
        # Use a package-relative path to locate the schema file so that
        # Database.connect works even if the current working directory is
        # changed (e.g., pytest tmp_path). This avoids FileNotFoundError
        # when tests run in isolated directories.
        base_dir = os.path.dirname(__file__)
        schema_path = os.path.join(base_dir, "schema.sql")
        if not os.path.exists(schema_path):
            # Fall back to legacy relative path for backward compatibility
            schema_path = SCHEMA_PATH

        with open(schema_path, "r", encoding="utf-8") as f:
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
