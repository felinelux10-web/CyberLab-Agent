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

def test_explicit_dialogue_continuation_is_local_even_when_parser_says_resume_system():
    memory = memory_with(
        {"user": "مرحبا", "assistant": "مرحبًا بك.", "target": ""},
        {"user": "كيف الحال", "assistant": "أنا جاهز للمحادثة. كيف تسير أمورك أنت؟", "target": ""},
    )

    for phrase in ("اكمل الحوار", "استكمال الحوار"):
        result = respond_locally(
            phrase,
            {"intent": "resume", "conversation_domain": "system",
             "conversation_act": "CONVERSATION_CONTINUATION"},
            memory,
        )

        assert result is not None, phrase
        assert result["status"] == "success", phrase
        assert result["source"] == "local_dialogue_engine", phrase
        assert result["executed"] is False, phrase
        assert "لم نحدد موضوعًا للنقاش بعد" in result["text"], phrase


def test_bare_continuation_is_not_stolen_from_a_latest_technical_exchange():
    memory = memory_with(
        {"user": "مرحبا", "assistant": "مرحبًا بك.", "target": ""},
        {"user": "حلل الخطأ", "assistant": "شرح تقني", "target": "Python",
         "context_kind": "execution", "conversation_domain": "technical"},
    )

    result = respond_locally(
        "اكمل",
        {"intent": "resume", "conversation_domain": "technical",
         "conversation_act": "CONVERSATION_CONTINUATION"},
        memory,
    )

    assert result is None


def test_one_word_how_question_gets_local_clarification_instead_of_provider_fallback():
    result = respond_locally(
        "كيف",
        {"intent": "resume", "conversation_domain": "system"},
        memory_with(),
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["source"] == "local_dialogue_engine"
    assert "لا تحدد ما الذي تسأل عنه" in result["text"]


def test_arabic_wellbeing_variants_are_recognized_locally():
    for phrase in (
        "كيف هي الاحوال", "كيف الأحوال", "كيف اخبارك",
        "كيف حالك اليوم", "هل انت بخير", "كيف كان يومك", "كيف حالك يا صديقي",
    ):
        result = respond_locally(
            phrase,
            {"intent": "personal_chat", "conversation_domain": "social",
             "conversation_act": "SOCIAL_CHECK_IN"},
            memory_with(),
        )
        assert result is not None, phrase
        assert result["source"] == "local_dialogue_engine", phrase
        assert "كيف تسير أمورك أنت" in result["text"], phrase

def test_wellbeing_reply_bypasses_system_resume_fallback_when_prior_turn_asked_about_wellbeing():
    memory = memory_with({
        "user": "كيف الحال",
        "assistant": "أنا جاهز للمحادثة. كيف تسير أمورك أنت؟",
        "target": "",
    })

    result = respond_locally(
        "بخير شكرا",
        {"intent": "resume", "conversation_domain": "system",
         "conversation_act": "CONVERSATION_CONTINUATION"},
        memory,
    )

    assert result is not None
    assert result["status"] == "success"
    assert "سعيد بأن أمورك بخير" in result["text"]


def test_common_friendly_social_acts_are_handled_offline_even_after_parser_fallback():
    cases = {
        "شكرا جزيلا": "على الرحب والسعة",
        "شكرا لك على المساعدة": "على الرحب والسعة",
        "اعتذر منك": "لا حاجة إلى الاعتذار",
        "اشعر بالملل": "تغيير الجو",
        "اشعر بالملل الشديد": "تغيير الجو",
        "اشعر بالوحدة": "يمكنك التحدث",
        "انا حزينة": "يومك ليس سهلًا",
        "انا حزينة جدا": "يومك ليس سهلًا",
        "انا سعيد": "الخبر الجميل",
        "احسنت": "شكرًا لك",
        "مع السلامة": "إلى اللقاء",
        "لا اعرف ماذا اقول": "نبدأ بسؤال بسيط",
    }

    for phrase, expected in cases.items():
        result = respond_locally(
            phrase,
            {"intent": "resume", "conversation_domain": "system"},
            memory_with(),
        )

        assert result is not None, phrase
        assert result["status"] == "success", phrase
        assert result["source"] == "local_dialogue_engine", phrase
        assert result["executed"] is False, phrase
        assert expected in result["text"], phrase


def test_local_social_response_normalizes_arabic_diacritics_and_punctuation():
    result = respond_locally(
        "شُكْرًا جَزِيلًا!",
        {"intent": "unclear", "conversation_domain": "general"},
        memory_with(),
    )

    assert result is not None
    assert "على الرحب والسعة" in result["text"]
    assert result["executed"] is False


def test_short_acknowledgement_does_not_override_unrelated_system_context():
    result = respond_locally(
        "تمام",
        {"intent": "resume", "conversation_domain": "system"},
        memory_with(),
    )

    assert result is None


def test_short_acknowledgement_in_dialogue_context_stays_with_current_topic():
    memory = memory_with({
        "user": "لنتحدث عن الفن",
        "assistant": "يمكننا الحديث عن الفن.",
        "target": "الفن",
    })

    result = respond_locally(
        "تمام",
        {"intent": "resume", "conversation_domain": "system"},
        memory,
    )

    assert result is not None
    assert result["target"] == "الفن"
    assert "الفن" in result["text"]
    assert result["executed"] is False


def test_operational_request_is_not_captured_by_friendly_dialogue_expansion():
    result = respond_locally(
        "حلل ملف Python ثم احفظ التقرير",
        {"intent": "analyze_code", "conversation_domain": "technical"},
        memory_with({"user": "شكرا", "assistant": "على الرحب", "target": ""}),
    )

    assert result is None


def test_arabic_greeting_and_casual_opening_variants_are_local():
    for phrase in (
        "أهلاً وسهلاً", "السلام عليكم ورحمة الله وبركاته",
        "صباح النور", "مساء النور", "تحية طيبة", "مرحبا يا صديقي",
    ):
        result = respond_locally(
            phrase,
            {"intent": "resume", "conversation_domain": "system"},
            memory_with(),
        )
        assert result is not None, phrase
        assert result["status"] == "success", phrase
        assert result["source"] == "local_social", phrase
        assert result["executed"] is False, phrase

    for phrase in (
        "هل يمكننا التحدث", "أريد التحدث معك",
        "أرغب في التحدث معك", "محادثة ودية",
    ):
        result = respond_locally(
            phrase,
            {"intent": "personal_chat", "conversation_domain": "social",
             "conversation_act": "CASUAL_CONVERSATION"},
            memory_with(),
        )
        assert result is not None, phrase
        assert result["source"] == "local_dialogue_engine", phrase
        assert result["executed"] is False, phrase


def test_topic_suggestions_are_local_and_written_in_standard_arabic():
    for phrase in (
        "اقترح لي بعض المواضيع",
        "اقترح موضوعا للنقاش",
        "مواضيع مثيرة للنقاش",
    ):
        result = respond_locally(
            phrase,
            {"intent": "resume", "conversation_domain": "system"},
            memory_with(),
        )

        assert result is not None, phrase
        assert result["source"] == "local_dialogue_engine", phrase
        assert "إليك بعض الموضوعات" in result["text"], phrase
        assert "واش" not in result["text"], phrase
        assert "شنو" not in result["text"], phrase
        assert result["executed"] is False, phrase
