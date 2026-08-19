import pytest

from lab_v4_dev.conversation.semantic_contract import (
    SemanticRequest,
    build_semantic_request,
)


def test_task_is_execution_and_requires_planning():
    r = build_semantic_request("حلل المشروع", "TASK")
    assert r.action_type == "execute"
    assert r.requires_planning is True


def test_question_is_analysis():
    r = build_semantic_request("ما وظيفة هذا الملف؟", "QUESTION")
    assert r.action_type == "analyze"
    assert r.requires_planning is False


def test_follow_up_can_require_context():
    r = build_semantic_request(
        "ماذا عن هذا؟",
        "FOLLOW_UP",
        requires_context=True,
    )
    assert r.requires_context is True
    assert r.action_type == "none"


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError):
        SemanticRequest(raw="x", mode="INVALID")


def test_confidence_is_bounded():
    with pytest.raises(ValueError):
        SemanticRequest(raw="x", mode="CHAT", confidence=1.1)
