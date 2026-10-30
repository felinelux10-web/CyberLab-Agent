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



def test_all_saved_dialogue_summaries_are_not_downgraded_to_live_dialogue():
    from lab_v4_dev.memory.session_state import session_selector

    for phrase in (
        "اكتب ملخص الجلسات كلها",
        "ملخص الجلسات المحفوظة كلها",
        "اعرض ملخص الجلسات كلها",
    ):
        selected = session_selector(phrase)
        assert selected == {"kind": "list", "report_mode": "summaries"}, (phrase, selected)



def test_fused_arabic_status_questions_reach_operational_status_handlers():
    from lab_v4_dev.intent.intent_parser import parse
    from lab_v4_dev.intent.intents import Intent

    for phrase in ("ماهي حالة الوكيل", "ما هي حالة الوكيل"):
        assert parse(phrase)["intent"] == Intent.STATUS

    for phrase in ("ماهي حالة النظام", "ما هي حالة النظام"):
        assert parse(phrase)["intent"] == Intent.SYSTEM_STATUS



def test_broad_memory_inventory_request_is_distinct_from_topic_recall():
    assert ConversationManager._is_memory_inventory_request(
        "ماذا تتذكر من خلال كل شيء تعرفه ومحفوظ عندك"
    )
    assert ConversationManager._is_memory_inventory_request("اعرض كل ما تتذكره")
    assert not ConversationManager._is_memory_inventory_request("هل تتذكر موضوع الفضاء؟")


def test_memory_inventory_is_local_and_reads_separate_memory_owners(monkeypatch):
    from lab_v4_dev.memory import session_state
    from lab_v4_dev.awareness import project_knowledge

    sessions = [
        {"session_id": "dialogue-1", "session_type": "dialogue"},
        {"session_id": "work-1", "session_type": "work"},
    ]
    monkeypatch.setattr(session_state, "get_session_index", lambda: sessions)
    monkeypatch.setattr(session_state, "get_recent_sessions", lambda: sessions)
    monkeypatch.setattr(
        session_state,
        "get_session_by_id",
        lambda session_id: {"session_id": session_id, "session_type": "dialogue" if session_id == "dialogue-1" else "work"},
    )
    monkeypatch.setattr(
        session_state,
        "build_session_brief_summary",
        lambda data: {
            "topic": "الفن" if data["session_type"] == "dialogue" else "إصلاح المشروع",
            "summary": "مناقشة فنية محفوظة" if data["session_type"] == "dialogue" else "تقدم عمل محفوظ",
            "session_type": data["session_type"],
        },
    )
    monkeypatch.setattr(
        project_knowledge,
        "get_project_state",
        lambda: {
            "version": "test-v1",
            "current_focus": "توحيد الذاكرة",
            "completed_count": 3,
            "last_goal": "إصلاح الاسترجاع",
            "last_step": "اختبار التلخيص",
            "active": ["تحسين الحوار"],
            "planned": ["تطوير Context API"],
        },
    )

    context = ContextStore()
    memory_store = SimpleNamespace(
        task_status_counts=lambda: {"done": 2},
        all_lessons=lambda: [{"lesson": "lesson-1"}],
    )
    orchestrator = SimpleNamespace(
        context=context,
        agent=SimpleNamespace(memory=memory_store),
    )
    manager = ConversationManager(orchestrator, DialogueMemory(context))

    result = manager._local_memory_inventory_answer()

    assert result["status"] == "success"
    assert result["source"] == "local_memory_inventory"
    assert "الجلسات المحفوظة: 2" in result["text"]
    assert "حوارات: 1" in result["text"]
    assert "عمل: 1" in result["text"]
    assert "الفن: مناقشة فنية محفوظة" in result["text"]
    assert "توحيد الذاكرة" in result["text"]
    assert "عدد الدروس المحفوظة: 1" in result["text"]


def test_memory_inventory_request_is_answered_before_provider_dispatch(monkeypatch):
    context = ContextStore()
    manager = ConversationManager(SimpleNamespace(context=context), DialogueMemory(context))
    calls = []
    monkeypatch.setattr(
        manager,
        "_local_memory_inventory_answer",
        lambda: calls.append("local") or {
            "status": "success",
            "intent": "memory_dump",
            "source": "local_memory_inventory",
            "text": "LOCAL MEMORY INVENTORY",
        },
    )

    result = manager.process("ماذا تتذكر من خلال كل شيء تعرفه ومحفوظ عندك")

    assert result["status"] == "success"
    assert result["source"] == "local_memory_inventory"
    assert calls == ["local"]



def test_provider_cannot_replace_cyberlab_identity_with_host_product_identity():
    fallback = "أنا CyberLab Agent داخل هذا المشروع."
    reply = (
        "أنا ChatGPT من OpenAI، وأخضع لسياسات OpenAI."
    )

    bounded = ConversationManager._bound_agent_self_reply(
        reply,
        "agent_identity",
        "من أنت؟",
        fallback=fallback,
    )

    assert bounded == fallback



def test_positive_acknowledgement_does_not_become_a_fake_dialogue_topic():
    from lab_v4_dev.conversation.unified_local_response import answer_local_response

    history = [
        {"role": "user", "content": "مرحبا", "conversation_domain": "social", "context_kind": "social"},
        {"role": "assistant", "content": "أهلًا بك. هل نبدأ من فكرة جديدة؟", "conversation_domain": "social", "context_kind": "dialogue"},
        {"role": "user", "content": "كيف الحال", "conversation_domain": "social", "context_kind": "social"},
        {"role": "assistant", "content": "أنا بخير، شكرًا لسؤالك. كيف حالك أنت؟", "conversation_domain": "social", "context_kind": "dialogue"},
        {"role": "user", "content": "جيد", "conversation_domain": "social", "context_kind": "social"},
        {"role": "assistant", "content": "أنا بخير، شكرًا لسؤالك. كيف حالك أنت؟", "conversation_domain": "social", "context_kind": "dialogue"},
    ]

    result = answer_local_response(
        "لنكمل حوارنا",
        {"intent": "personal_chat", "conversation_act": "CONVERSATION_CONTINUATION"},
        {"conversation_act": "CONVERSATION_CONTINUATION", "conversation_domain": "general"},
        history=history,
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["local_strategy"] == "friendly_dialogue_reopen"
    assert "لم نحدد موضوعًا" in result["text"]
    assert "جيد" not in result["text"]
