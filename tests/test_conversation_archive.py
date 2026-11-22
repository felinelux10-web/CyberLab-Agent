import sqlite3
from types import SimpleNamespace

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
