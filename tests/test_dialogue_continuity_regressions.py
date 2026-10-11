from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics


class RecordingOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {
            "status": "success",
            "intent": (parsed or {}).get("intent"),
            "text": "رد التنفيذ",
        }


def _manager(monkeypatch):
    calls = []

    def fake_gateway(prompt, **kwargs):
        calls.append((prompt, kwargs))
        if "طلب المستخدم الحالي: اكتب ملخص" in prompt or "ماذا كنا نقول" in prompt:
            answer = "ملخص: بدأ الحوار بموضوع عام، ثم طلب المستخدم الاستمرار في السياق نفسه."
        else:
            answer = f"رد حواري رقم {len(calls)}"
        return {"status": "success", "text": answer, "provider_used": "test"}

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        fake_gateway,
    )
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    return ConversationManager(orchestrator, memory), memory, orchestrator, calls


def test_same_dialogue_continuation_does_not_become_work_resume_clarification(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)

    first = manager.process("ماذا تستطيع فعله؟")
    assert first["status"] == "success"
    assert memory.active_context_entity() is None

    continued = manager.process("نعم نكمل في نفس سياق الموضوع")

    assert continued["status"] == "success"
    assert continued["source"] != "conversation_manager"
    assert "استكمال الحوار السابق أم استكمال العمل" not in continued.get("text", "")
    assert len(calls) == 2
    assert "رد حواري رقم 1" in calls[-1][0]
    assert orchestrator.calls == []


def test_dialogue_summary_request_returns_summary_not_transcript(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    manager.process("ماذا تستطيع فعله؟")
    result = manager.process("اكتب ملخص حوار الجلسة")

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "summary"
    assert result["text"].startswith("ملخص:")
    assert "المستخدم:" not in result["text"]
    assert "الوكيل:" not in result["text"]
    assert "لا تنسخ الحوار" in calls[-1][0]
    assert orchestrator.calls == []


def test_short_summary_phrase_is_resolved_as_dialogue_history():
    continuation = classify_conversation_semantics("نعم نكمل في نفس سياق الموضوع")
    assert continuation["conversation_act"] == "CONVERSATION_CONTINUATION"

    for text in ("ملخص الحوار", "ملخص حوار الجلسة", "اكتب ملخص الحوار"):
        result = classify_conversation_semantics(text)
        assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
        assert result["response_attributes"]["dialogue_response_mode"] == "summary"


def test_last_question_retrieves_last_user_message_without_dumping_history(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    manager.process("ماذا تستطيع فعله؟")
    result = manager.process("ما آخر سؤال سألتك أنا؟")

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "last_question"
    assert "ماذا تستطيع فعله؟" in result["text"]
    assert "المستخدم:" not in result["text"]
    assert orchestrator.calls == []


def test_question_about_unsolicited_explanation_is_dialogue_history():
    result = classify_conversation_semantics("من طلب منك هذا الشرح؟")
    assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert result["response_attributes"]["dialogue_response_mode"] == "answer"


def test_explicit_dialogue_continuation_excludes_saved_work_turns(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.add_turn(
        role="user",
        content="استكمل العمل في الملف secret.py",
        context_kind="work",
        conversation_domain="work",
    )
    memory.state.add_turn(
        role="assistant",
        content="تفاصيل عمل لا يجب إدخالها في الحوار العام",
        context_kind="work",
        conversation_domain="work",
    )
    manager.process("ماذا تستطيع فعله؟")
    result = manager.process("نعم نكمل في نفس سياق الموضوع")

    assert result["status"] == "success"
    assert len(calls) == 2
    assert "تفاصيل عمل لا يجب إدخالها" not in calls[-1][0]
    assert "secret.py" not in calls[-1][0]

def test_topic_restore_uses_archived_exchange_after_turn_window_rolls_over():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    # The bounded turn list now contains only a different, newer branch.
    for role in ("user", "assistant") * 4:
        memory.state.add_turn(
            role=role,
            content="محتوى أحدث لا يخص اللوحة",
            target="موضوع أحدث",
            intent="cyber_explain",
            conversation_domain="technical",
            context_kind="dialogue",
        )

    memory.state.exchange_archive = [
        {
            "user": "استخدمت الذهب والبيج والأزرق الداكن في اللوحة",
            "assistant": "هذه الألوان تخلق تباينًا بين الدفء والبرودة.",
            "target": "اللوحة الفنية",
            "intent": "personal_chat",
            "conversation_domain": "general",
            "context_kind": "dialogue",
        },
        {
            "user": "تفاصيل عمل سرية",
            "assistant": "رد عمل سري",
            "target": "اللوحة الفنية",
            "intent": "modify_file",
            "conversation_domain": "work",
            "context_kind": "work",
        },
    ]

    restored = manager._history_for_transition(
        ContextTransition.RESTORE,
        {"target": "اللوحة الفنية"},
    )
    text = " ".join(turn["content"] for turn in restored)

    assert "الذهب والبيج والأزرق الداكن" in text
    assert "تخلق تباينًا" in text
    assert "تفاصيل عمل سرية" not in text
    assert "رد عمل سري" not in text


def test_new_session_resets_dialogue_memory_even_without_orchestrator_reset_hook(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.last_topic = "موضوع قديم"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.exchange_archive = [{
        "user": "معلومة قديمة",
        "assistant": "رد قديم",
        "context_kind": "dialogue",
        "conversation_domain": "general",
    }]

    result = manager.process("جلسة جديدة")

    assert result["status"] == "success"
    assert memory.state.last_topic is None
    assert memory.state.exchange_archive == []
