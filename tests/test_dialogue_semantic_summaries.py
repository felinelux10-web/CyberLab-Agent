from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.memory.session_state import (
    _dialogue_exchange_insights,
    build_session_brief_summary,
    build_session_restore_summary,
    summarize_dialogue_exchanges,
)


def _exchange(session_id, user, assistant, target=""):
    return {
        "session_id": session_id,
        "user": user,
        "assistant": assistant,
        "target": target,
        "context_kind": "dialogue",
        "conversation_domain": "general",
    }


def _saved_dialogue(exchanges, *, topic=""):
    return {
        "session_id": "saved-dialogue-record",
        "session_type": "dialogue",
        "status": "completed",
        "dialogue_state": {
            "session_id": "dialogue-state-1",
            "last_topic": topic,
            "exchange_archive": exchanges,
        },
    }


def test_how_are_you_exchange_is_not_misclassified_as_how_to_content():
    exchange = _exchange(
        "dialogue-state-1",
        "كيف الحال؟",
        "أنا بخير، شكرًا لسؤالك. هل هناك موضوع تود مناقشته؟",
        "كيف الحال",
    )

    assert _dialogue_exchange_insights(exchange) == []

    summary = build_session_restore_summary(
        _saved_dialogue([exchange], topic="كيف الحال")
    )
    assert "كيفية تنفيذ أمر أو فهمه" not in summary
    assert "لم يتجاوز السجل تبادل التحية" in summary


def test_saved_dialogue_summary_describes_meaning_without_printing_messages():
    user_message = "ما الفرق بين الفن التجريدي والنقش البارز؟"
    assistant_message = (
        "الفن التجريدي يعتمد على الأشكال والألوان للتعبير دون محاكاة مباشرة "
        "للعالم المرئي. أما النقش البارز فيعتمد على تشكيل سطح ذي بروز محسوس."
    )
    exchange = _exchange(
        "dialogue-state-1",
        user_message,
        assistant_message,
        "الفن التجريدي والنقش البارز",
    )
    saved = _saved_dialogue([exchange], topic="الفن التجريدي والنقش البارز")

    summary = build_session_restore_summary(saved)
    brief = build_session_brief_summary(saved)

    assert "قارن الحوار بين" in summary
    assert "الفن التجريدي والنقش البارز" in summary
    assert "المستخدم:" not in summary
    assert "الوكيل:" not in summary
    assert user_message not in summary
    assert assistant_message not in summary
    assert "الخلاصة الدلالية للحوار" in brief["summary"]
    assert "الفن التجريدي والنقش البارز" in brief["summary"]
    assert user_message not in brief["summary"]
    assert assistant_message not in brief["summary"]


def test_shared_dialogue_summarizer_reports_topic_and_stop_point():
    exchanges = [
        _exchange(
            "dialogue-state-1",
            "ما الفرق بين الرسم والنحت؟",
            "الرسم يعالج الصورة على سطح مستو، بينما النحت يبني شكلًا مجسمًا.",
            "الرسم والنحت",
        ),
        _exchange(
            "dialogue-state-1",
            "وماذا عن النقش البارز؟",
            "يعتمد النقش البارز على بروز الأشكال من خلفية مستوية.",
            "النقش البارز",
        ),
    ]

    report = summarize_dialogue_exchanges(exchanges, topic="الفنون", limit=4)

    assert report["topic"] == "الفنون"
    assert report["meaningful_exchange_count"] == 2
    assert report["has_substantive_content"] is True
    assert "النقش البارز" in report["stop_point"]
    assert report["insights"]
    assert all("المستخدم:" not in item and "الوكيل:" not in item for item in report["insights"])


def test_live_dialogue_summary_is_narrative_not_a_message_dump():
    context = ContextStore()
    memory = DialogueMemory(context)
    session_id = memory.state.session_id
    exchanges = [
        _exchange(
            session_id,
            "ما الفرق بين الرسم والنحت؟",
            "الرسم يعتمد على سطح مستو، والنحت ينتج هيئة مجسمة.",
            "الرسم والنحت",
        ),
        _exchange(
            session_id,
            "وماذا عن النقش البارز؟",
            "تظهر عناصره فوق خلفية منخفضة، فينشأ اختلاف محسوس في الارتفاع.",
            "النقش البارز",
        ),
    ]
    manager = ConversationManager(SimpleNamespace(context=context), memory)

    result = manager._answer_dialogue_history(
        "اكتب ملخص الحوار",
        "summary",
        exchanges,
    )

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["text"].startswith("ملخص الحوار الحالي:")
    assert "ما الفرق بين الرسم والنحت؟" not in result["text"]
    assert "وماذا عن النقش البارز؟" not in result["text"]
    assert "المستخدم:" not in result["text"]
    assert "الوكيل:" not in result["text"]
    assert "نقطة التوقف:" in result["text"]
    assert "النقش البارز" in result["text"]



def test_natural_dialogue_continuations_are_classified_without_template_wording():
    from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics

    for phrase in (
        "لنكمل حوارنا",
        "هيا نكمل حديثنا",
        "حسنا هيا نكمل حديثنا",
        "دعنا نواصل حديثنا",
    ):
        result = classify_conversation_semantics(phrase)
        assert result["conversation_act"] == "CONVERSATION_CONTINUATION", (phrase, result)


def test_last_dialogue_stopping_point_question_routes_to_local_summary():
    from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics

    result = classify_conversation_semantics("ماهي اخر نقطة توقف فيها الحوار")

    assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert result["response_attributes"]["dialogue_response_mode"] == "summary"
