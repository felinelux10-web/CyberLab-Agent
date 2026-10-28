from lab_v4_dev.conversation.unified_local_response import answer_local_response


def test_greeting_uses_available_dialogue_context_without_fixed_universal_reply():
    history = [
        {"role": "user", "content": "أريد الحديث عن الفن التجريدي", "target": "الفن التجريدي", "context_kind": "dialogue"},
        {"role": "assistant", "content": "يمكننا النظر إلى الألوان والأشكال ومعانيها.", "target": "الفن التجريدي", "context_kind": "dialogue"},
    ]
    result = answer_local_response(
        "مرحبا",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_GREETING", "target": "الفن التجريدي"},
        {"conversation_act": "SOCIAL_GREETING", "conversation_domain": "general"},
        history=history,
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["source"] == "local_social_engine"
    assert "الفن التجريدي" in result["text"]
    assert result["executed"] is False


def test_continuation_composes_reply_from_user_and_assistant_history():
    history = [
        {"role": "user", "content": "لماذا يستخدم الفنانون التباين اللوني؟", "target": "التباين اللوني", "context_kind": "dialogue"},
        {"role": "assistant", "content": "يساعد التباين على إبراز العناصر وتوجيه الانتباه.", "target": "التباين اللوني", "context_kind": "dialogue"},
    ]
    result = answer_local_response(
        "أكمل",
        {"intent": "personal_chat", "conversation_act": "CONVERSATION_CONTINUATION", "target": "التباين اللوني"},
        {"conversation_act": "CONVERSATION_CONTINUATION", "conversation_domain": "general", "target": "التباين اللوني"},
        history=history,
    )

    assert result is not None
    assert "لماذا يستخدم الفنانون التباين اللوني؟" in result["text"]
    assert "يساعد التباين على إبراز العناصر" in result["text"]
    assert result["local_strategy"] == "semantic_context_composition"


def test_local_suggestion_uses_current_topic_instead_of_unrelated_generic_template():
    history = [
        {"role": "user", "content": "أهتم بالرسم التجريدي", "target": "الرسم التجريدي", "context_kind": "dialogue"},
        {"role": "assistant", "content": "يمكننا مناقشة العلاقة بين اللون والشكل.", "target": "الرسم التجريدي", "context_kind": "dialogue"},
    ]
    result = answer_local_response(
        "ماذا تقترح علي الآن؟",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_FOLLOW_UP", "target": "الرسم التجريدي"},
        {"conversation_act": "SOCIAL_FOLLOW_UP", "conversation_domain": "general", "target": "الرسم التجريدي"},
        history=history,
    )

    assert result is not None
    assert "الرسم التجريدي" in result["text"]
    assert "أهتم بالرسم التجريدي" in result["text"]


def test_local_engine_refuses_project_or_operational_turns():
    result = answer_local_response(
        "شغّل الاختبارات",
        {"intent": "run_tests", "conversation_act": "CONVERSATION_CONTINUATION", "conversation_domain": "project"},
        {"conversation_act": "CONVERSATION_CONTINUATION", "conversation_domain": "project"},
        history=[],
    )

    assert result is None


def test_local_engine_does_not_fabricate_answer_for_unknown_factual_question():
    result = answer_local_response(
        "ما أحدث اكتشاف علمي اليوم؟",
        {"intent": "personal_chat", "conversation_act": "NONE", "conversation_domain": "general"},
        {"conversation_act": "NONE", "conversation_domain": "general"},
        history=[],
    )

    assert result is None


def test_local_continuation_without_history_requests_the_missing_anchor():
    result = answer_local_response(
        "أكمل من آخر نقطة",
        {"intent": "personal_chat", "conversation_act": "CONVERSATION_CONTINUATION"},
        {"conversation_act": "CONVERSATION_CONTINUATION", "conversation_domain": "general"},
        history=[],
    )

    assert result is not None
    assert "لا أجد في السياق المتاح" in result["text"]



def test_greeting_wording_changes_the_local_response_by_meaning():
    common = {"intent": "personal_chat", "conversation_act": "SOCIAL_GREETING"}
    semantic = {"conversation_act": "SOCIAL_GREETING", "conversation_domain": "general"}
    hello = answer_local_response("أهلا", common, semantic)
    salam = answer_local_response("السلام عليكم", common, semantic)

    assert hello is not None and salam is not None
    assert hello["text"] != salam["text"]
    assert "أهلًا" in hello["text"]
    assert "وعليكم السلام" in salam["text"]


def test_unresolved_continuation_is_not_reported_as_a_successful_turn():
    result = answer_local_response(
        "أكمل",
        {"intent": "personal_chat", "conversation_act": "CONVERSATION_CONTINUATION"},
        {"conversation_act": "CONVERSATION_CONTINUATION", "conversation_domain": "general"},
        history=[],
    )

    assert result is not None
    assert result["status"] == "needs_clarification"

def test_social_opening_uses_last_completed_exchange_even_without_topic_metadata():
    history = [
        {
            "role": "user",
            "content": "أريد الحديث عن الفن التجريدي",
            "conversation_domain": "general",
            "context_kind": "dialogue",
        },
        {
            "role": "assistant",
            "content": "يمكننا النظر إلى اللون والشكل والمعنى.",
            "conversation_domain": "general",
            "context_kind": "dialogue",
        },
    ]
    result = answer_local_response(
        "دعنا نتحدث قليلا",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_OPENING"},
        {"conversation_act": "SOCIAL_OPENING", "conversation_domain": "general"},
        history=history,
    )

    assert result is not None
    assert "أريد الحديث عن الفن التجريدي" in result["text"]
    assert "اللون والشكل والمعنى" in result["text"]


def test_general_social_response_does_not_reuse_stale_project_or_technical_history():
    history = [
        {
            "role": "user",
            "content": "اشرح Buffer Overflow",
            "target": "Buffer Overflow",
            "conversation_domain": "technical",
            "context_kind": "dialogue",
        },
        {
            "role": "assistant",
            "content": "شرح تقني سابق",
            "target": "Buffer Overflow",
            "conversation_domain": "technical",
            "context_kind": "dialogue",
        },
    ]
    result = answer_local_response(
        "مرحبا",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_GREETING"},
        {"conversation_act": "SOCIAL_GREETING", "conversation_domain": "general"},
        history=history,
    )

    assert result is not None
    assert "Buffer Overflow" not in result["text"]
    assert "شرح تقني سابق" not in result["text"]

def test_explicit_technical_continuation_keeps_authorized_technical_history():
    history = [
        {
            "role": "user",
            "content": "اشرح Buffer Overflow",
            "target": "Buffer Overflow",
            "conversation_domain": "technical",
            "context_kind": "dialogue",
        },
        {
            "role": "assistant",
            "content": "يحدث عند تجاوز البيانات حدود الذاكرة المخصصة.",
            "target": "Buffer Overflow",
            "conversation_domain": "technical",
            "context_kind": "dialogue",
        },
    ]
    result = answer_local_response(
        "أكمل",
        {
            "intent": "personal_chat",
            "conversation_act": "CONVERSATION_CONTINUATION",
            "conversation_domain": "technical",
            "target": "Buffer Overflow",
        },
        {
            "conversation_act": "CONVERSATION_CONTINUATION",
            "conversation_domain": "technical",
            "target": "Buffer Overflow",
        },
        history=history,
    )

    assert result is not None
    assert "اشرح Buffer Overflow" in result["text"]
    assert "تجاوز البيانات حدود الذاكرة" in result["text"]
