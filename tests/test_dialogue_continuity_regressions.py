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

    first = manager.process("دعنا نناقش موضوعًا عامًا")
    assert first["status"] == "success"

    continued = manager.process("نعم نكمل في نفس سياق الموضوع")

    assert continued["status"] == "success"
    assert continued["source"] != "conversation_manager"
    assert "استكمال الحوار السابق أم استكمال العمل" not in continued.get("text", "")
    assert len(calls) == 2
    assert "رد حواري رقم 1" in calls[-1][0]
    assert orchestrator.calls == []


def test_dialogue_summary_request_returns_summary_not_transcript(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    manager.process("دعنا نناقش موضوعًا عامًا")
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
    for text in ("ملخص الحوار", "ملخص حوار الجلسة", "اكتب ملخص الحوار"):
        result = classify_conversation_semantics(text)
        assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
        assert result["response_attributes"]["dialogue_response_mode"] == "summary"


def test_last_question_retrieves_last_user_message_without_dumping_history(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    manager.process("دعنا نناقش موضوعًا عامًا")
    result = manager.process("ما آخر سؤال سألتك أنا؟")

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "last_question"
    assert "دعنا نناقش موضوعًا عامًا" in result["text"]
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
    manager.process("دعنا نناقش موضوعًا عامًا")
    result = manager.process("نعم نكمل في نفس سياق الموضوع")

    assert result["status"] == "success"
    assert len(calls) == 2
    assert "تفاصيل عمل لا يجب إدخالها" not in calls[-1][0]
    assert "secret.py" not in calls[-1][0]
