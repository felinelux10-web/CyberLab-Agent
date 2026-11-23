import sqlite3
from types import SimpleNamespace

from lab_v4_dev.core.agent import Agent
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.memory.conversation_archive import ConversationArchive


def make_archive():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    return ConversationArchive(SimpleNamespace(conn=connection))


def test_append_search_and_read_neighboring_exchanges():
    archive = make_archive()
    first = archive.append_exchange(
        session_id="session-a",
        user_text="I make relief art with gypsum plaster.",
        assistant_text="You described a plaster relief process.",
    )
    archive.append_exchange(
        session_id="session-a",
        user_text="The layer is about three centimeters thick.",
        assistant_text="The thickness you specified is about three centimeters.",
    )
    hits = archive.search_messages("gypsum", session_id="session-a")
    assert hits
    assert hits[0]["speaker"] == "user"
    context = archive.read_context(hits[0]["id"], before=1, after=1)
    assert len(context) == 4
    assert {row["exchange_id"] for row in context} >= {first}


def test_fact_provenance_is_preserved():
    archive = make_archive()
    fact_id = archive.save_fact(
        subject="user",
        predicate="uses_material",
        value="water-based paint",
        speaker="user",
        source_kind="explicit",
        source_session_id="session-72",
        source_exchange_id="exchange-1",
        confidence=1.0,
    )
    facts = archive.search_facts("water-based")
    assert facts[0]["id"] == fact_id
    assert facts[0]["source_session_id"] == "session-72"
    assert facts[0]["speaker"] == "user"


def test_skill_outcomes_are_counted_and_retrievable():
    archive = make_archive()
    skill_id = archive.save_skill(
        name="safe-session-export",
        description="Export a saved session without mutating its source.",
        steps=["read source", "write separate export", "verify checksum"],
        preconditions=["source session exists"],
    )
    archive.record_skill_run(skill_id, success=True, notes="verified")
    archive.record_skill_run(skill_id, success=False, notes="permission denied")
    skill = archive.search_skills("safe-session-export")[0]
    assert skill["success_count"] == 1
    assert skill["failure_count"] == 1
    assert skill["steps"][0] == "read source"


def test_explicit_first_person_statement_becomes_provenance_fact():
    archive = make_archive()
    archive.append_exchange(
        session_id="session-72",
        user_text="أنا أستعمل الصباغة المائية.",
        assistant_text="سأحتفظ بهذه المعلومة بوصفها تصريحًا منك.",
    )
    facts = archive.search_relevant_facts("ما الصباغة التي أستخدمها؟")
    assert facts
    assert facts[0]["value"] == "الصباغة المائية"
    assert facts[0]["speaker"] == "user"
    assert facts[0]["source_session_id"] == "session-72"
    assert facts[0]["evidence_message_id"] is not None


def test_structured_fact_backfill_migrates_existing_sqlite_exchanges_once():
    archive = make_archive()
    sid = "preexisting-sqlite-dialogue"
    exchange_id = "preexisting-raw-exchange"
    archive.conn.execute(
        """INSERT INTO conversation_sessions
           (session_id,title,created_at,updated_at) VALUES (?,?,?,?)""",
        (sid, "Existing dialogue", "2026-11-01T10:00:00", "2026-11-01T10:00:00"),
    )
    archive.conn.executemany(
        """INSERT INTO conversation_messages
           (session_id,exchange_id,exchange_index,speaker,content,source,intent,
            topic,metadata_json,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            (sid, exchange_id, 1, "user", "أصب الجبس بسماكة ثلاثة سنتيمترات.",
             "legacy_json", "personal_chat", "لوحة الجبس", "{}", "2026-11-01T10:00:00"),
            (sid, exchange_id, 1, "assistant", "سجلت السماكة.",
             "legacy_json", "personal_chat", "لوحة الجبس", "{}", "2026-11-01T10:00:00"),
        ],
    )
    archive.conn.commit()

    result = archive.migrate_structured_dialogue_facts()
    assert result["imported_sessions"] == 1
    assert result["imported_exchanges"] == 1
    assert result["imported_facts"] >= 2
    assert any(
        item["value"] == "ثلاثة سنتيمترات"
        for item in archive.search_relevant_facts("ثلاثة سنتيمترات")
    )
    assert archive.migrate_structured_dialogue_facts()["already_migrated"] is True


def test_legacy_dialogue_migration_is_idempotent_and_searchable():
    archive = make_archive()
    record = {
        "session_id": "legacy-session-72",
        "session_type": "dialogue",
        "title": "Gypsum relief painting",
        "dialogue_state": {
            "session_id": "legacy-session-72",
            "transcript_archive": [
                {
                    "session_id": "legacy-session-72",
                    "exchange_id": "legacy-exchange-1",
                    "timestamp": "2026-11-01T10:00:00",
                    "user": "أنا أستعمل الصباغة المائية.",
                    "assistant": "فهمت، الصباغة المائية هي التي تستخدمها.",
                },
                {
                    "session_id": "legacy-session-72",
                    "exchange_id": "legacy-exchange-2",
                    "timestamp": "2026-11-01T10:01:00",
                    "user": "أصب الجبس بسماكة ثلاثة سنتيمترات.",
                    "assistant": "سجلت السماكة التي ذكرتها.",
                },
            ],
        },
    }
    result = archive.migrate_legacy_dialogue_sessions([record])
    assert result["imported_sessions"] == 1
    assert result["imported_exchanges"] == 2
    hits = archive.search_messages("ثلاثة سنتيمترات", session_id="legacy-session-72")
    assert hits
    transcript = archive.load_exchanges("legacy-session-72")
    assert len(transcript) == 2
    facts = archive.search_relevant_facts("ما الصباغة التي أستخدمها؟")
    assert facts and facts[0]["value"] == "الصباغة المائية"
    structured = archive.conn.execute(
        """SELECT 1 FROM memory_facts
           WHERE source_exchange_id='legacy-exchange-2'
             AND predicate='thickness' AND source_kind='structured'"""
    ).fetchone()
    assert structured is not None
    second = archive.migrate_legacy_dialogue_sessions([record])
    assert second["already_migrated"] is True


def test_saved_session_view_merges_sqlite_transcript_without_losing_legacy_data(tmp_path, monkeypatch):
    import sqlite3
    from lab_v4_dev.memory import db as memory_db
    from lab_v4_dev.memory.session_state import _attach_sqlite_dialogue_transcript

    database_path = tmp_path / "archive.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """CREATE TABLE conversation_messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            exchange_id TEXT,
            exchange_index INTEGER,
            speaker TEXT,
            content TEXT,
            source TEXT,
            intent TEXT,
            topic TEXT,
            metadata_json TEXT,
            created_at TEXT
        )"""
    )
    connection.executemany(
        """INSERT INTO conversation_messages
           (session_id,exchange_id,exchange_index,speaker,content,source,intent,
            topic,metadata_json,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            ("saved-72", "sqlite-1", 1, "user", "I used gypsum.", "conversation",
             "personal_chat", "relief art", "{}", "2026-11-01T10:00:00"),
            ("saved-72", "sqlite-1", 1, "assistant", "You used gypsum.", "conversation",
             "personal_chat", "relief art", "{}", "2026-11-01T10:00:00"),
        ],
    )
    connection.commit()
    connection.close()
    monkeypatch.setattr(memory_db, "DB_PATH", str(database_path))

    legacy = {
        "session_id": "saved-72",
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": "saved-72",
            "exchange_archive": [
                {
                    "session_id": "saved-72",
                    "user": "Earlier legacy exchange",
                    "assistant": "Earlier response",
                    "timestamp": "2026-10-31T10:00:00",
                }
            ],
        },
    }
    merged = _attach_sqlite_dialogue_transcript(legacy, "saved-72")
    transcript = merged["dialogue_state"]["transcript_archive"]
    assert len(transcript) == 2
    assert transcript[0]["user"] == "Earlier legacy exchange"
    assert transcript[1]["user"] == "I used gypsum."
    assert merged["_transcript_source"] == "legacy+sqlite"

def test_agent_archives_provider_backed_dialogue_as_conversation_evidence():
    calls = []
    session_id = "provider-dialogue-session"
    result = {
        "status": "success",
        "executed": False,
        "intent": Intent.CYBER_EXPLAIN,
        "text": "شرح محفوظ من مزود المعرفة.",
        "route_decision": SimpleNamespace(
            route="P-TOOL",
            evidence_scope="none",
        ),
    }
    agent = object.__new__(Agent)
    agent.loop = True
    agent.state = SimpleNamespace(mode="normal")
    agent._save_dialogue_checkpoint = lambda: None
    agent.conv_manager = SimpleNamespace(process=lambda _text: result)
    snapshots = [
        {"session_id": session_id, "last_topic": "شرح تقني", "exchange_archive": []},
        {
            "session_id": session_id, "last_topic": "شرح تقني",
            "exchange_archive": [{
                "session_id": session_id,
                "exchange_id": "canonical-provider-exchange",
                "exchange_index": 1,
                "timestamp": "2026-11-23T12:00:00+00:00",
                "user": "اشرح موضوعًا تقنيًا",
                "assistant": "شرح محفوظ من مزود المعرفة.",
                "target": "شرح تقني",
                "context_kind": "dialogue",
                "conversation_domain": "technical",
                "conversation_act": "TOPIC_QUERY",
                "context_transition": "new_independent",
                "knowledge_version": 3,
            }],
        },
        {
            "session_id": session_id, "last_topic": "شرح تقني",
            "exchange_archive": [{
                "session_id": session_id,
                "exchange_id": "canonical-provider-exchange",
                "exchange_index": 1,
                "timestamp": "2026-11-23T12:00:00+00:00",
                "user": "اشرح موضوعًا تقنيًا",
                "assistant": "شرح محفوظ من مزود المعرفة.",
                "target": "شرح تقني",
                "context_kind": "dialogue",
                "conversation_domain": "technical",
                "conversation_act": "TOPIC_QUERY",
                "context_transition": "new_independent",
                "knowledge_version": 3,
            }],
        },
    ]
    agent.dialogue_memory = SimpleNamespace(
        snapshot=lambda: snapshots.pop(0),
        state=SimpleNamespace(session_id=session_id),
    )
    agent.memory = SimpleNamespace(
        conversations=SimpleNamespace(
            append_exchange=lambda **exchange: calls.append(exchange) or "exchange-1"
        )
    )
    agent.session = SimpleNamespace(session_id=session_id)

    returned = agent.run("اشرح موضوعًا تقنيًا")

    assert returned is result
    assert len(calls) == 1
    assert calls[0]["session_id"] == session_id
    assert calls[0]["user_text"] == "اشرح موضوعًا تقنيًا"
    assert calls[0]["assistant_text"] == "شرح محفوظ من مزود المعرفة."
    assert calls[0]["status"] == "success"
    assert calls[0]["exchange_id"] == "canonical-provider-exchange"
    assert calls[0]["exchange_index"] == 1
    assert calls[0]["created_at"] == "2026-11-23T12:00:00+00:00"
    assert calls[0]["metadata"]["conversation_domain"] == "technical"

def test_append_exchange_is_idempotent_and_preserves_canonical_identity():
    archive = make_archive()
    kwargs = {
        "session_id": "canonical-session",
        "exchange_id": "stable-exchange-id",
        "exchange_index": 7,
        "created_at": "2026-11-23T12:00:00+00:00",
        "user_text": "أصب الجبس بسماكة ثلاثة سنتيمترات.",
        "assistant_text": "تم تسجيل السماكة.",
        "metadata": {
            "context_kind": "dialogue",
            "conversation_domain": "technical",
            "conversation_act": "TOPIC_QUERY",
            "recall_only": False,
        },
    }
    first = archive.append_exchange(**kwargs)
    second = archive.append_exchange(**kwargs)
    assert first == second == "stable-exchange-id"
    rows = archive.conn.execute(
        "SELECT * FROM conversation_messages WHERE session_id=?",
        ("canonical-session",),
    ).fetchall()
    assert len(rows) == 2
    assert {row["exchange_id"] for row in rows} == {"stable-exchange-id"}
    assert {row["exchange_index"] for row in rows} == {7}
    assert all("conversation_domain" in row["metadata_json"] for row in rows)
    structured = archive.conn.execute(
        """SELECT predicate, value, status FROM memory_facts
           WHERE source_session_id=? AND source_exchange_id=? AND source_kind='structured'""",
        ("canonical-session", "stable-exchange-id"),
    ).fetchall()
    assert {(row["predicate"], row["value"]) for row in structured} == {
        ("thickness", "ثلاثة سنتيمترات"),
        ("material", "الجبس"),
    }
    assert all(row["status"] == "active" for row in structured)
    assert any(
        item["predicate"] == "thickness"
        for item in archive.search_relevant_facts("ثلاثة سنتيمترات")
    )


def test_structured_facts_keep_assistant_suggestions_out_of_user_memory():
    from lab_v4_dev.memory.dialogue_knowledge import _extract_structured_facts

    extracted = _extract_structured_facts(
        "يمكنك استخدام ورق الصنفرة لتنعيم الحواف."
    )
    assert any(
        item["attribute"] == "tool" and item["value"] == "ورق الصنفرة"
        for item in extracted
    )
    archive = make_archive()
    archive.append_exchange(
        session_id="speaker-separated-session",
        exchange_id="assistant-tool-suggestion",
        exchange_index=1,
        user_text="كيف أنعم حواف الجبس؟",
        assistant_text="يمكنك استخدام ورق الصنفرة لتنعيم الحواف.",
        topic="تشطيب الجبس",
    )
    assistant_facts = archive.search_facts(
        "ورق الصنفرة", speaker="assistant", source_kind="structured"
    )
    assert any(
        item["subject"] == "assistant"
        and item["speaker"] == "assistant"
        and item["value"] == "ورق الصنفرة"
        for item in assistant_facts
    )
    assert not archive.search_relevant_facts("ورق الصنفرة")


def test_structured_correction_supersedes_only_the_prior_topic_fact():
    archive = make_archive()
    archive.append_exchange(
        session_id="correction-fact-session",
        exchange_id="old-thickness",
        exchange_index=1,
        user_text="كانت سماكة طبقة الجبس ثلاثة سنتيمترات.",
        assistant_text="سجلت السماكة.",
        topic="لوحة الجبس",
    )
    archive.append_exchange(
        session_id="correction-fact-session",
        exchange_id="new-thickness",
        exchange_index=2,
        user_text="بل، التصحيح أن السماكة خمسة سنتيمترات.",
        assistant_text="تم اعتماد التصحيح.",
        topic="لوحة الجبس",
    )
    rows = archive.conn.execute(
        """SELECT source_exchange_id, value, status FROM memory_facts
           WHERE source_session_id=? AND predicate='thickness' AND source_kind='structured'""",
        ("correction-fact-session",),
    ).fetchall()
    by_exchange = {row["source_exchange_id"]: row for row in rows}
    assert by_exchange["old-thickness"]["status"] == "superseded"
    assert by_exchange["new-thickness"]["status"] == "active"
    assert by_exchange["new-thickness"]["value"] == "خمسة سنتيمترات"


def test_agent_does_not_persist_read_only_history_without_new_exchange():
    calls = []
    session_id = "read-only-history-session"
    snapshot = {
        "session_id": session_id,
        "exchange_archive": [{
            "session_id": session_id,
            "exchange_id": "existing-exchange",
            "user": "ما الذي ناقشناه سابقًا؟",
            "assistant": "تحدثنا عن الجبس.",
        }],
    }
    result = {
        "status": "success",
        "executed": False,
        "intent": Intent.CYBER_EXPLAIN,
        "text": "تحدثنا عن الجبس.",
        "route_decision": SimpleNamespace(route="L-FACT", evidence_scope="live_exchanges"),
    }
    agent = object.__new__(Agent)
    agent.loop = True
    agent.state = SimpleNamespace(mode="normal")
    agent.conv_manager = SimpleNamespace(process=lambda _text: result)
    agent.dialogue_memory = SimpleNamespace(
        snapshot=lambda: dict(snapshot),
        state=SimpleNamespace(session_id=session_id),
    )
    agent.memory = SimpleNamespace(
        conversations=SimpleNamespace(
            append_exchange=lambda **exchange: calls.append(exchange)
        )
    )
    agent.session = SimpleNamespace(session_id=session_id)

    returned = agent.run("ما الذي ناقشناه سابقًا؟")

    assert returned is result
    assert calls == []


def test_personal_fact_search_excludes_assistant_suggestions():
    archive = make_archive()
    archive.save_user_fact(
        subject="user",
        predicate="uses_material",
        value="الصباغة المائية",
        source_session_id="session-72",
        source_exchange_id="user-fact-1",
        confidence=0.94,
    )
    archive.save_assistant_suggestion(
        subject="user",
        predicate="recommended_material",
        value="الصباغة الزيتية",
        source_session_id="session-72",
        source_exchange_id="assistant-suggestion-1",
        confidence=0.90,
    )

    personal_facts = archive.search_relevant_facts(
        "ما الصباغة التي أستخدمها؟"
    )
    assistant_suggestions = archive.search_facts(
        "الصباغة", speaker="assistant"
    )

    assert personal_facts
    assert all(item["speaker"] == "user" for item in personal_facts)
    assert any(item["value"] == "الصباغة المائية" for item in personal_facts)
    assert not any(item["value"] == "الصباغة الزيتية" for item in personal_facts)
    assert any(item["value"] == "الصباغة الزيتية" for item in assistant_suggestions)

def test_legacy_migration_repairs_nested_identity_only_with_provenance():
    archive = make_archive()
    record = {
        "session_id": "saved-checkpoint-72",
        "session_type": "dialogue",
        "title": "جلسة الحوار 72",
        "dialogue_state": {
            "session_id": "live-dialogue-72",
            "transcript_archive": [{
                "session_id": "saved-checkpoint-72",
                "exchange_id": "legacy-nested-identity-1",
                "context_kind": "dialogue",
                "conversation_domain": "general",
                "user": "أستخدم الصباغة المائية.",
                "assistant": "تم تسجيل نوع الصباغة الذي ذكرته.",
                "response_status": "success",
            }],
        },
    }

    result = archive.migrate_legacy_dialogue_sessions([record])
    exchanges = archive.load_exchanges("live-dialogue-72")

    assert result["imported_exchanges"] == 1
    assert len(exchanges) == 1
    assert exchanges[0]["session_id"] == "live-dialogue-72"
    assert exchanges[0]["exchange_id"] == "legacy-nested-identity-1"
    assert exchanges[0]["user"] == "أستخدم الصباغة المائية."


def test_empty_legacy_index_does_not_consume_migration_marker():
    archive = make_archive()
    migration_key = "legacy_dialogue_transcripts_v2_provenance_repair"

    result = archive.migrate_legacy_dialogue_sessions([])

    assert result["status"] == "no_source_records"
    assert archive.migration_complete(migration_key) is False

def test_migration_retries_dialogue_records_whose_transcript_was_not_loaded():
    archive = make_archive()
    migration_key = "legacy_dialogue_transcripts_v2_provenance_repair"
    record = {
        "session_id": "late-loaded-dialogue",
        "session_type": "dialogue",
        "dialogue_state": {},
    }

    first = archive.migrate_legacy_dialogue_sessions([record])
    assert first["status"] == "no_dialogue_transcripts"
    assert archive.migration_complete(migration_key) is False

    record["dialogue_state"] = {
        "session_id": "late-loaded-dialogue",
        "transcript_archive": [{
            "session_id": "late-loaded-dialogue",
            "exchange_id": "late-loaded-exchange",
            "user": "أستخدم إطارًا خشبيًا.",
            "assistant": "تم تسجيل ذلك.",
        }],
    }
    second = archive.migrate_legacy_dialogue_sessions([record])

    assert second["status"] == "migrated"
    assert second["imported_exchanges"] == 1
    assert archive.migration_complete(migration_key) is True

def test_reusable_skill_search_requires_a_better_than_failed_run_history():
    archive = make_archive()
    validated_id = archive.save_skill(
        name="safe-session-export",
        description="Export a session without modifying its source.",
        steps=["read source", "write separate file", "verify checksum"],
        preconditions=["saved session exists"],
    )
    archive.record_skill_run(validated_id, success=True)
    archive.record_skill_run(validated_id, success=True)
    archive.record_skill_run(validated_id, success=False)

    unvalidated_id = archive.save_skill(
        name="untested-session-cleanup",
        description="Cleanup session data.",
        steps=["delete old session"],
        preconditions=["explicit approval"],
    )
    failed_id = archive.save_skill(
        name="unsafe-session-reset",
        description="Reset session data.",
        steps=["reset database"],
        preconditions=["backup exists"],
    )
    archive.record_skill_run(failed_id, success=False)
    archive.record_skill_run(failed_id, success=False)

    results = archive.search_relevant_skills("safe session export", limit=5)
    result_ids = {item["id"] for item in results}

    assert validated_id in result_ids
    assert unvalidated_id not in result_ids
    assert failed_id not in result_ids



def test_message_search_falls_back_when_existing_fts_index_is_incomplete():
    archive = make_archive()
    assert archive.fts_available
    archive.append_exchange(
        session_id="fts-fallback-session",
        user_text="أنا أستخدم الصباغة المائية في اللوحة.",
        assistant_text="سجلت المعلومة.",
    )
    archive.conn.execute("DELETE FROM conversation_messages_fts")
    archive.conn.commit()

    hits = archive.search_messages(
        "الصباغة المائية",
        session_id="fts-fallback-session",
    )

    assert len(hits) == 1
    assert hits[0]["speaker"] == "user"
    assert "الصباغة المائية" in hits[0]["content"]


def test_relevant_skill_requires_a_positive_success_majority():
    archive = make_archive()
    skill_id = archive.save_skill(
        name="verified-archive-export",
        description="Export a saved archive without changing its source.",
        steps=["read archive", "write a separate export", "verify output"],
        preconditions=["archive exists"],
    )

    assert archive.search_relevant_skills("archive export") == []

    archive.record_skill_run(skill_id, success=True, notes="verified")
    assert archive.search_relevant_skills("archive export")

    archive.record_skill_run(skill_id, success=False, notes="verification failed")
    assert archive.search_relevant_skills("archive export") == []
