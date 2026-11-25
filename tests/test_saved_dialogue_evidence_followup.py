"""Saved-dialogue factual follow-ups must use exact-session source evidence."""

from lab_v4_dev.conversation.conversation_manager import ConversationManager


def _saved_dialogue(session_id="saved-72"):
    return {
        "session_id": session_id,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": session_id,
            "transcript_archive": [
                {
                    "session_id": session_id,
                    "exchange_id": f"{session_id}:6",
                    "exchange_index": 6,
                    "user": "أصب الجبس في الإطار الخشبي بسماكة نحو 3 سم.",
                    "assistant": "يمكنك تركه حتى يجف.",
                }
            ],
        },
    }


def test_saved_detail_question_uses_exact_saved_session_evidence(monkeypatch):
    from lab_v4_dev.memory import session_state, dialogue_knowledge

    session_id = "saved-72"
    saved = _saved_dialogue(session_id)
    evidence = [{
        "session_id": session_id,
        "exchange_id": f"{session_id}:6",
        "exchange_index": 6,
        "score": 2.4,
        "matched_terms": ["جبس", "سماكة"],
        "matched_user_terms": ["جبس", "سماكة"],
        "matched_assistant_terms": [],
        "user": "أصب الجبس في الإطار الخشبي بسماكة نحو 3 سم.",
        "assistant": "يمكنك تركه حتى يجف.",
    }]
    monkeypatch.setattr(session_state, "get_session_by_id", lambda value: saved)
    monkeypatch.setattr(dialogue_knowledge, "retrieve_dialogue_evidence", lambda data, query, limit=8: evidence)
    monkeypatch.setattr(
        dialogue_knowledge,
        "format_dialogue_evidence_answer",
        lambda data, query, limit=8, evidence=None: "السماكة نحو 3 سم [التبادل 6].",
    )

    result = ConversationManager._saved_dialogue_evidence_answer(
        "ما سماكة الجبس؟", session_id,
    )

    assert result is not None
    assert result["session_id"] == session_id
    assert result["evidence_scope"] == "saved_session"
    assert result["provider_used"] is False
    assert result["evidence_exchange_ids"] == [f"{session_id}:6"]
    assert "3 سم" in result["text"]


def test_saved_detail_formatter_extracts_the_user_stated_thickness():
    from lab_v4_dev.memory.dialogue_knowledge import format_dialogue_evidence_answer

    saved = _saved_dialogue("saved-72")
    evidence = [{
        "session_id": "saved-72",
        "exchange_id": "saved-72:6",
        "exchange_index": 6,
        "user": "أصب الجبس في الإطار الخشبي بسماكة نحو 3 سم.",
        "assistant": "يمكنك تركه حتى يجف.",
        "matched_terms": ["جبس", "سماكة"],
        "score": 2.4,
    }]

    answer = format_dialogue_evidence_answer(
        saved, "ما سماكة الجبس؟", evidence=evidence,
    )

    assert "السماكة: 3 سم" in answer
    assert "[التبادل 6" in answer
    assert "ما قاله المستخدم" in answer


def test_saved_detail_retrieval_rejects_cross_session_evidence(monkeypatch):
    from lab_v4_dev.memory import session_state, dialogue_knowledge

    saved = _saved_dialogue("saved-72")
    monkeypatch.setattr(session_state, "get_session_by_id", lambda value: saved)
    monkeypatch.setattr(
        dialogue_knowledge,
        "retrieve_dialogue_evidence",
        lambda data, query, limit=8: [{
            "session_id": "another-session",
            "exchange_id": "another-session:2",
            "exchange_index": 2,
            "matched_terms": ["جبس"],
        }],
    )

    result = ConversationManager._saved_dialogue_evidence_answer(
        "ما سماكة الجبس؟", "saved-72",
    )

    assert result is None


def test_saved_detail_retrieval_rejects_non_question_and_unmatched_evidence(monkeypatch):
    from lab_v4_dev.memory import session_state, dialogue_knowledge

    saved = _saved_dialogue("saved-72")
    monkeypatch.setattr(session_state, "get_session_by_id", lambda value: saved)
    monkeypatch.setattr(
        dialogue_knowledge,
        "retrieve_dialogue_evidence",
        lambda data, query, limit=8: [{
            "session_id": "saved-72",
            "exchange_id": "saved-72:6",
            "exchange_index": 6,
            "matched_terms": [],
        }],
    )

    assert ConversationManager._saved_dialogue_evidence_answer(
        "أريد الانتقال إلى موضوع آخر", "saved-72",
    ) is None
    assert ConversationManager._saved_dialogue_evidence_answer(
        "ما سماكة الجبس؟", "saved-72",
    ) is None
