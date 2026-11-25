"""Temporal fact validity and correction provenance remain additive and traceable."""

import sqlite3
from types import SimpleNamespace

from lab_v4_dev.memory.conversation_archive import ConversationArchive
from lab_v4_dev.memory.dialogue_knowledge import analyze_dialogue_session


def test_dialogue_correction_invalidates_only_the_matching_structured_attribute():
    session_id = "temporal-dialogue-session"
    session = {
        "session_id": session_id,
        "dialogue_state": {
            "session_id": session_id,
            "exchange_archive": [
                {
                    "session_id": session_id,
                    "exchange_id": "old-description",
                    "exchange_index": 1,
                    "timestamp": "2026-01-01T10:00:00",
                    "target": "لوحة الجبس",
                    "user": "أستخدم إطارًا خشبيًا وأصب الجبس بسماكة ثلاثة سنتيمترات.",
                    "assistant": "تم تسجيل وصف اللوحة.",
                },
                {
                    "session_id": session_id,
                    "exchange_id": "corrected-thickness",
                    "exchange_index": 2,
                    "timestamp": "2026-01-02T10:00:00",
                    "target": "لوحة الجبس",
                    "user": "بل، التصحيح أن السماكة خمسة سنتيمترات.",
                    "assistant": "تم تسجيل التصحيح.",
                },
            ],
        },
    }

    analysis = analyze_dialogue_session(session)
    old_record = next(
        item for item in analysis["knowledge"]
        if item["source_exchange_id"] == "old-description"
        and any(fact.get("attribute") == "thickness" for fact in item["structured_facts"])
    )
    correction = next(
        item for item in analysis["user_corrections"]
        if item["source_exchange_id"] == "corrected-thickness"
    )
    old_thickness = next(
        fact for fact in old_record["structured_facts"]
        if fact.get("attribute") == "thickness"
    )
    old_frame = next(
        fact for fact in old_record["structured_facts"]
        if fact.get("attribute") == "frame_material"
    )
    new_thickness = next(
        fact for fact in correction["structured_facts"]
        if fact.get("attribute") == "thickness"
    )

    assert old_thickness["invalidated_at"] == "2026-01-02T10:00:00"
    assert old_thickness["status"] == "superseded"
    assert old_frame["invalidated_at"] is None
    assert old_record["status"] != "superseded"
    assert correction["origin"] == "user"
    assert correction["verification"] == "validated"
    assert new_thickness["supersedes"] == old_record["knowledge_id"]
    assert correction["supersedes"] == [old_record["knowledge_id"]]


def test_sqlite_fact_correction_keeps_old_value_and_records_temporal_link():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    archive = ConversationArchive(SimpleNamespace(conn=connection))
    session_id = "temporal-sqlite-session"
    topic = "لوحة الجبس"

    old_cursor = connection.execute(
        """INSERT INTO conversation_messages
           (session_id,exchange_id,exchange_index,speaker,content,created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            session_id, "old-thickness", 1, "user",
            "كانت سماكة طبقة الجبس ثلاثة سنتيمترات.",
            "2026-01-01T10:00:00",
        ),
    )
    archive._store_structured_facts(
        session_id=session_id,
        exchange_id="old-thickness",
        speaker="user",
        text="كانت سماكة طبقة الجبس ثلاثة سنتيمترات.",
        topic=topic,
        evidence_message_id=int(old_cursor.lastrowid),
        created_at="2026-01-01T10:00:00",
    )

    new_cursor = connection.execute(
        """INSERT INTO conversation_messages
           (session_id,exchange_id,exchange_index,speaker,content,created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            session_id, "new-thickness", 2, "user",
            "بل، التصحيح أن السماكة خمسة سنتيمترات.",
            "2026-01-02T10:00:00",
        ),
    )
    archive._store_structured_facts(
        session_id=session_id,
        exchange_id="new-thickness",
        speaker="user",
        text="بل، التصحيح أن السماكة خمسة سنتيمترات.",
        topic=topic,
        evidence_message_id=int(new_cursor.lastrowid),
        created_at="2026-01-02T10:00:00",
        correction=True,
    )

    rows = connection.execute(
        """SELECT * FROM memory_facts
           WHERE source_session_id=? AND predicate='thickness'
           ORDER BY id""",
        (session_id,),
    ).fetchall()
    assert len(rows) == 2
    old, new = rows
    assert old["value"] == "ثلاثة سنتيمترات"
    assert old["status"] == "superseded"
    assert old["invalidated_at"] == "2026-01-02T10:00:00"
    assert new["value"] == "خمسة سنتيمترات"
    assert new["status"] == "active"
    assert new["valid_from"] == "2026-01-02T10:00:00"
    assert new["invalidated_at"] is None
    assert new["supersedes"] == old["id"]
    assert old["verification"] == "validated"
    assert new["verification"] == "validated"
    assert new["origin"] == "user"

    active = archive.search_facts(
        "thickness", speaker="user", source_kind="structured",
    )
    assert [item["id"] for item in active] == [new["id"]]
    history = archive.get_fact_history(
        source_session_id=session_id, predicate="thickness",
    )
    assert [item["status"] for item in history] == ["superseded", "active"]
    assert history[0]["invalidated_at"] == history[1]["valid_from"]
    connection.close()



def test_temporal_fact_schema_upgrades_existing_rows_without_replacing_them():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE memory_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            value TEXT NOT NULL,
            speaker TEXT NOT NULL DEFAULT 'user',
            source_kind TEXT NOT NULL DEFAULT 'explicit',
            source_session_id TEXT,
            source_exchange_id TEXT,
            evidence_message_id INTEGER,
            confidence REAL NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL DEFAULT 'active',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """INSERT INTO memory_facts
           (subject,predicate,value,speaker,source_kind,created_at,updated_at)
           VALUES ('user','paint_type','الصباغة المائية','user','structured',
                   '2026-01-01T10:00:00','2026-01-01T10:00:00')"""
    )

    ConversationArchive(SimpleNamespace(conn=connection))
    row = connection.execute(
        "SELECT * FROM memory_facts WHERE predicate='paint_type'"
    ).fetchone()

    assert row["value"] == "الصباغة المائية"
    assert row["valid_from"] == "2026-01-01T10:00:00"
    assert row["invalidated_at"] is None
    assert row["supersedes"] is None
    assert row["verification"] == "candidate"
    assert row["origin"] == "user"
    connection.close()



def test_fact_validator_rejects_mismatched_source_session():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    archive = ConversationArchive(SimpleNamespace(conn=connection))
    cursor = connection.execute(
        """INSERT INTO conversation_messages
           (session_id,exchange_id,exchange_index,speaker,content,created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            "actual-session", "actual-exchange", 1, "user",
            "أستخدم الصباغة المائية.",
            "2026-04-01T10:00:00",
        ),
    )

    fact_id = archive.save_fact(
        subject="user",
        predicate="paint_type",
        value="الصباغة المائية",
        speaker="user",
        source_kind="structured",
        source_session_id="wrong-session",
        source_exchange_id="actual-exchange",
        evidence_message_id=int(cursor.lastrowid),
        origin="user",
    )
    fact = connection.execute(
        "SELECT * FROM memory_facts WHERE id=?",
        (fact_id,),
    ).fetchone()

    import json
    metadata = json.loads(fact["metadata_json"])
    assert fact["verification"] == "rejected"
    assert metadata["validation"]["reason"] == "source_session_mismatch"
    assert archive.search_facts("paint_type", speaker="user") == []
    connection.close()
