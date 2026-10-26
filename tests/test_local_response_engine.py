from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.local_response_engine import answer_local_social


def test_semantically_classified_greeting_has_a_local_response():
    result = answer_local_social(
        "أهلًا وسهلًا",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_GREETING"},
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["source"] == "local_social_engine"
    assert result["executed"] is False
    assert "مرحبًا" in result["text"]


def test_social_fallback_is_reached_through_conversation_manager():
    result = ConversationManager._local_social_answer(
        "أهلًا وسهلًا",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_GREETING"},
    )

    assert result is not None
    assert result["source"] == "local_social_engine"


def test_knowledge_or_execution_act_does_not_get_a_generic_local_social_reply():
    result = answer_local_social(
        "اشرح آلية التوجيه في المشروع",
        {"intent": "cyber_explain", "conversation_act": "NONE"},
    )

    assert result is None
