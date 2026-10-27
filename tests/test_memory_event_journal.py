import json
import sqlite3

from lab_v4_dev.memory import db as db_module
from lab_v4_dev.memory.db import Database


def test_database_event_journal_is_bounded_and_queryable(monkeypatch, tmp_path):
    database_path = tmp_path / "agent.db"
    schema_path = tmp_path / "schema.sql"
    schema_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS memory_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memory_events_owner_id
            ON memory_events(owner, id DESC);
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(db_module, "DB_PATH", str(database_path))
    monkeypatch.setattr(db_module, "SCHEMA_PATH", str(schema_path))
    db = Database()
    db.connect()
    try:
        for index in range(7):
            db.record_event("tests", "turn", {"sequence": index}, limit=100)
        events = db.recent_events(3, owner="tests")
        assert len(events) == 3
        assert json.loads(events[0]["payload_json"])["sequence"] == 6
        assert db.integrity_check() is True
    finally:
        db.close()


def test_lesson_search_uses_similarity_without_returning_match_score():
    from lab_v4_dev.memory.lessons import Lessons

    class FakeDB:
        def fetchone(self, query, params=()):
            return None
        def fetchall(self, query, params=()):
            return [
                {"id": 1, "error_pattern": "pytest fails because fixture path is wrong",
                 "solution": "Use the correct fixture path", "success_count": 2,
                 "total_count": 2},
                {"id": 2, "error_pattern": "database connection timeout",
                 "solution": "Increase timeout", "success_count": 1, "total_count": 3},
            ]

    result = Lessons(FakeDB()).find("pytest fixture path is wrong")
    assert result is not None
    assert result["id"] == 1
    assert "match_score" not in result
