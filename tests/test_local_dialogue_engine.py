from types import SimpleNamespace

from lab_v4_dev.conversation.local_dialogue_engine import respond_locally


def memory_with(*exchanges):
    state = SimpleNamespace(
        session_id="session-1",
        exchange_archive=[
            {"session_id": "session-1", "context_kind": "dialogue",
             "conversation_domain": "general", **item}
            for item in exchanges
        ],
    )
    return SimpleNamespace(state=state)


def test_casual_opening_is_handled_locally_without_fixed_greeting_reply():
    result = respond_locally(
        "لنتحدث قليلا",
        {"intent": "personal_chat", "conversation_domain": "social",
         "conversation_act": "CASUAL_CONVERSATION"},
        memory_with(),
    )

    assert result is not None
    assert result["source"] == "local_dialogue_engine"
    assert result["executed"] is False
    assert "بكل سرور" in result["text"]
    assert "أي موضوع يهمك" in result["text"]


def test_wellbeing_acknowledgement_uses_prior_dialogue_context():
    memory = memory_with({
        "user": "كيف الحال",
        "assistant": "أنا جاهز للمحادثة. كيف حالك أنت؟",
        "target": "",
    })

    result = respond_locally(
        "بخير شكرا",
        {"intent": "personal_chat", "conversation_domain": "social",
         "conversation_act": "SOCIAL_ACKNOWLEDGEMENT"},
        memory,
    )

    assert result is not None
    assert result["source"] == "local_dialogue_engine"
    assert "سعيد بأن أمورك بخير" in result["text"]
    assert result["text"] != memory.state.exchange_archive[-1]["assistant"]


def test_ambiguous_what_uses_previous_answer_and_requests_specific_clarification():
    memory = memory_with({
        "user": "لنتحدث قليلا",
        "assistant": "يمكننا مناقشة الفن أو الأفكار أو الحياة اليومية.",
        "target": "",
    })

    result = respond_locally(
        "ماذا",
        {"intent": "personal_chat", "conversation_domain": "general",
         "conversation_act": "CLARIFICATION_REQUEST"},
        memory,
    )

    assert result is not None
    assert "الفن أو الأفكار أو الحياة اليومية" in result["text"]
    assert "أي جزء" in result["text"]


def test_agent_identity_can_be_answered_offline_even_if_parser_marks_system_domain():
    result = respond_locally(
        "من انت",
        {"intent": "agent_identity", "conversation_domain": "system"},
        memory_with(),
    )

    assert result is not None
    assert "لا أملك نموذجًا لغويًا محليًا عامًا مثبتًا" in result["text"]


def test_unavailable_general_factual_knowledge_is_not_fabricated_locally():
    result = respond_locally(
        "ما أسباب نشوء الفن التجريدي؟",
        {"intent": "personal_chat", "conversation_domain": "general",
         "conversation_act": "NONE"},
        memory_with(),
    )

    assert result is None


def test_technical_request_is_not_stolen_by_social_responder():
    result = respond_locally(
        "حلل هذا الخطأ في Python",
        {"intent": "cyber_explain", "conversation_domain": "technical"},
        memory_with(),
    )

    assert result is None
