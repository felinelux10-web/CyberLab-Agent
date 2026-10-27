import json
import os

from lab_v4_dev.memory.intelligence import (
    atomic_write_json, memory_metadata, normalize_memory_text,
    rank_memory_records, score_memory_record,
)


def test_memory_normalization_handles_arabic_variants_without_mutating_source():
    source = "الفَنّ التَجريدي والنحت البارز"
    assert normalize_memory_text(source) == normalize_memory_text("الفن التجريدي والنحت البارز")
    assert source == "الفَنّ التَجريدي والنحت البارز"


def test_memory_ranking_scores_relevance_before_applying_limit():
    records = [
        {"session_id": "recent-unrelated", "title": "جلسة SQL وحقن قواعد البيانات", "updated_at": "2099-01-01"},
        {"session_id": "older-relevant", "title": "الفن التجريدي والنحت البارز", "updated_at": "2020-01-01"},
        {"session_id": "weak", "title": "الفن والتاريخ", "updated_at": "2025-01-01"},
    ]
    ranked = rank_memory_records("الفن التجريدي والنحت البارز", records,
        fields=("title",), minimum_score=0.12, limit=1)
    assert len(ranked) == 1 and ranked[0]["session_id"] == "older-relevant"
    assert ranked[0]["match_score"] > score_memory_record(
        "الفن التجريدي والنحت البارز", records[0], fields=("title",))


def test_memory_metadata_has_provenance_and_lifecycle_fields():
    metadata = memory_metadata("technical_knowledge", source="test",
        confidence="test_verified", importance=1.4, scope="project")
    assert metadata["record_version"] == 1
    assert metadata["memory_type"] == "technical_knowledge"
    assert metadata["source"] == "test"
    assert metadata["importance"] == 1.0
    assert metadata["status"] == "ACTIVE"
    assert metadata["access_count"] == 0 and metadata["last_accessed_at"] is None


def test_atomic_json_write_leaves_complete_document_and_honors_private_mode(tmp_path):
    path = tmp_path / "private" / "memory.json"
    payload = {"schema_version": 1, "records": {"x": {"value": "محفوظ"}}}
    atomic_write_json(str(path), payload, mode=0o600)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert not list(path.parent.glob("*.tmp"))
    assert not list(path.parent.glob(".*.tmp"))


def test_session_search_ranks_all_candidates_before_limiting(monkeypatch):
    from lab_v4_dev.memory import session_state
    monkeypatch.setattr(session_state, "get_session_index", lambda: [
        {"session_id": "new-unrelated", "title": "SQL injection", "updated_at": "2099-01-01"},
        {"session_id": "old-art", "title": "الفن التجريدي والنحت البارز", "updated_at": "2020-01-01"},
        {"session_id": "medium-art", "title": "الفن والرسم", "updated_at": "2025-01-01"},
    ])
    results = session_state.search_sessions("الفن التجريدي والنحت البارز", limit=1)
    assert [item["session_id"] for item in results] == ["old-art"]


def test_knowledge_base_search_prefers_relevant_alias_and_updates_access(monkeypatch):
    from lab_v4_dev.awareness import knowledge_base as kb
    data = {"schema_version": kb.KB_SCHEMA_VERSION, "records": {
        "sql injection": {"canonical_key": "sql injection", "aliases": ["حقن SQL"],
            "answer": "إجابة SQL", "status": "ACTIVE", "importance": 0.5,
            "access_count": 0, "hits": 0, "updated_at": "2099-01-01"},
        "net tcp three way handshake": {"canonical_key": "net tcp three way handshake",
            "aliases": ["TCP handshake", "المصافحة الثلاثية في TCP"],
            "answer": "إجابة TCP", "status": "ACTIVE", "importance": 0.5,
            "access_count": 0, "hits": 0, "updated_at": "2020-01-01"},
    }}
    monkeypatch.setattr(kb, "_load", lambda: data)
    monkeypatch.setattr(kb, "_save", lambda value: None)
    assert kb.search("شرح TCP handshake") == "إجابة TCP"
    assert data["records"]["net tcp three way handshake"]["access_count"] == 1
    assert data["records"]["sql injection"]["access_count"] == 0


def test_context_store_extracts_full_semantic_versions_and_ranks_history():
    from lab_v4_dev.context.context_store import ContextStore

    store = ContextStore()
    store.update("current_version", "CyberLab Agent v5.9.13-dev")
    assert store.current_version == "5.9.13-dev"
    store.update("explain", "SQL injection")
    store.update("discuss", "الفن التجريدي والنحت البارز")
    ranked = store.search_history("الفن التجريدي والنحت البارز", limit=1)
    assert ranked
    assert ranked[0]["target"] == "الفن التجريدي والنحت البارز"
    assert "match_score" in ranked[0]
    snapshot = store.snapshot()
    assert snapshot["memory_type"] == "short_term_execution_context"
    assert len(snapshot["history"]) == 3


def test_dialogue_context_identity_normalizes_arabic_diacritics():
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.context.context_store import ContextStore

    memory = DialogueMemory(ContextStore())
    assert memory._same_topic("الفَنّ التَجريدي", "الفن التجريدي")


def test_personal_memory_new_store_uses_current_schema_version(tmp_path):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryStore
    store = PersonalMemoryStore(str(tmp_path / "private" / "personal.json"))
    assert store._load()["schema_version"] == 2


def test_legacy_knowledge_records_are_migrated_in_memory_without_losing_content(monkeypatch, tmp_path):
    from lab_v4_dev.awareness import knowledge_base as kb
    legacy = {
        "schema_version": 1,
        "records": {
            "dns cache": {
                "answer": "A cached DNS answer",
                "aliases": "DNS caching",
                "created_at": "2024-01-01T00:00:00",
            }
        },
    }
    path = tmp_path / "legacy_knowledge.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setattr(kb, "_kb_path", lambda: str(path))
    migrated = kb._load()
    record = migrated["records"]["dns cache"]
    assert record["answer"] == "A cached DNS answer"
    assert record["canonical_key"] == "dns cache"
    assert record["aliases"] == ["DNS caching"]
    assert record["memory_type"] == "technical_knowledge"
