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
    agent.conv_manager = SimpleNamespace(process=lambda _text: result)
    agent.dialogue_memory = SimpleNamespace(
        snapshot=lambda: {"session_id": session_id, "last_topic": "شرح تقني"},
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

