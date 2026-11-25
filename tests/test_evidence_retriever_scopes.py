"""EvidenceRetriever enforces explicit dialogue ownership scopes."""

import pytest

from lab_v4_dev.memory.evidence_retriever import EvidenceRetriever


def test_retriever_rejects_unknown_scope():
    with pytest.raises(ValueError):
        EvidenceRetriever.retrieve("سؤال", scope="implicit")


def test_saved_scope_rejects_mismatched_session_identity(monkeypatch):
    from lab_v4_dev.memory import session_state

    monkeypatch.setattr(
        session_state,
        "get_session_by_id",
        lambda session_id: {
            "session_id": "different-session",
            "session_type": "dialogue",
            "dialogue_state": {},
        },
    )

    assert EvidenceRetriever.retrieve(
        "ما التفاصيل؟", scope="saved", session_id="requested-session",
    ) == []


def test_live_scope_never_reads_a_different_live_session():
    state = {
        "session_id": "live-a",
        "exchange_archive": [{
            "session_id": "live-a",
            "exchange_id": "live-a:1",
            "user": "معلومة أصلية",
            "assistant": "رد",
        }],
    }

    assert EvidenceRetriever.retrieve(
        "معلومة", scope="live", session_id="live-b", live_state=state,
    ) == []


def test_live_scope_ranks_only_exact_session_evidence(monkeypatch):
    from lab_v4_dev.memory import dialogue_knowledge

    state = {
        "session_id": "live-a",
        "exchange_archive": [{
            "session_id": "live-a",
            "exchange_id": "live-a:1",
            "exchange_index": 1,
            "user": "أستخدم الجبس.",
            "assistant": "حسنًا.",
        }],
    }
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state._load_sqlite_dialogue_exchanges",
        lambda session_id: [],
    )
    monkeypatch.setattr(
        dialogue_knowledge,
        "retrieve_dialogue_evidence",
        lambda data, query, limit=8: [{
            "session_id": data["session_id"],
            "exchange_id": "live-a:1",
            "exchange_index": 1,
            "matched_terms": ["جبس"],
            "score": 1.2,
        }],
    )

    result = EvidenceRetriever.retrieve(
        "الجبس", scope="live", session_id="live-a", live_state=state,
    )

    assert len(result) == 1
    assert result[0]["evidence_scope"] == "live"
    assert result[0]["source_session_id"] == "live-a"
    assert result[0]["exchange_id"] == "live-a:1"


def test_saved_scope_accepts_valid_nested_dialogue_owner(monkeypatch):
    from lab_v4_dev.memory import session_state, dialogue_knowledge

    record = {
        "session_id": "saved-checkpoint",
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": "dialogue-owner",
            "transcript_archive": [{
                "session_id": "dialogue-owner",
                "exchange_id": "dialogue-owner:4",
                "exchange_index": 4,
                "user": "المعلومة الأصلية",
                "assistant": "الرد",
                "context_kind": "dialogue",
                "conversation_domain": "general",
            }],
        },
    }
    monkeypatch.setattr(session_state, "get_session_by_id", lambda session_id: record)
    monkeypatch.setattr(
        dialogue_knowledge,
        "retrieve_completed_dialogue_exchanges",
        lambda data: ("dialogue-owner", data["dialogue_state"]["transcript_archive"]),
    )
    monkeypatch.setattr(
        dialogue_knowledge,
        "retrieve_dialogue_evidence",
        lambda data, query, limit=8: [{
            "session_id": "dialogue-owner",
            "exchange_id": "dialogue-owner:4",
            "exchange_index": 4,
            "matched_terms": ["معلومة"],
            "score": 0.9,
        }],
    )

    result = EvidenceRetriever.retrieve(
        "المعلومة", scope="saved", session_id="saved-checkpoint",
    )

    assert len(result) == 1
    assert result[0]["session_id"] == "dialogue-owner"
    assert result[0]["source_session_id"] == "saved-checkpoint"
    assert result[0]["evidence_scope"] == "saved"
