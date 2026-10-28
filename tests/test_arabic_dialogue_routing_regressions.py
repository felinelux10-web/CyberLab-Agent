from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics


class RecordingOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {"status": "success", "text": "رد تنفيذ غير متوقع"}


def _manager(monkeypatch):
    calls = []

    def fake_gateway(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": f"رد سياقي رقم {len(calls)}",
            "provider_used": "test",
        }

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        fake_gateway,
    )
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    return ConversationManager(orchestrator, memory), calls


def test_general_ai_agents_are_not_cyberlab_self_queries():
    result = parse(
        "بصراحة اريد اعرف اكثر عن الذكاء الصناعي وخصوصا وكلاء الذكاء الصناعي"
    )
    assert result["intent"] == "personal_chat"
    assert result.get("conversation_domain") in {"social", "general"}


def test_correction_of_project_scope_becomes_dialogue_correction():
    result = classify_conversation_semantics(
        "لا لم اقصد وكيل ذكاء صناعي ل cyberlab_agent بل وكلاء الذكاء الصناعي بصفة عامة"
    )
    assert result["conversation_act"] == "CORRECTION"


def test_reply_reference_is_not_agent_execution_flow():
    result = parse("حسنا لكنمل اذن ماهو ردك على كلامي")
    assert result["intent"] == "personal_chat"
    assert result["conversation_act"] == "CONVERSATION_CONTINUATION"


def test_arabic_typo_normalization_recognizes_history_and_summary():
    result = classify_conversation_semantics("ايها الخردة قلت اكتب ملهص بما كنا نناقشه")
    assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert result["response_attributes"]["dialogue_response_mode"] == "summary"


def test_general_continuation_does_not_ask_work_or_dialogue_choice(monkeypatch):
    manager, calls = _manager(monkeypatch)
    manager.process("فقط اريد الدردشة معك")
    result = manager.process(
        "نعم سنكمل حوارنا في محادثة ودية كنا نقول ونريد ان ندردش قليلا"
    )
    assert result["status"] == "success"
    assert result["source"] == "llm"
    assert "استكمال الحوار السابق أم استكمال العمل" not in result["text"]
    assert len(calls) == 2


def test_relation_to_dialogue_is_contextual_chat_not_archive_dump(monkeypatch):
    manager, calls = _manager(monkeypatch)
    manager.process("نتحدث عن الذكاء الاصطناعي بشكل عام")
    result = manager.process("ما علاقة هذا بما كنا نقوله")
    assert result["status"] == "success"
    assert result["source"] == "llm"
    assert "dialogue_response_mode" not in result
    assert len(calls) == 2


def test_typo_summary_returns_current_archive_content(monkeypatch):
    manager, _ = _manager(monkeypatch)
    user_turn = "نتحدث عن وكلاء الذكاء الصناعي بصفة عامة"
    manager.process(user_turn)
    result = manager.process("ناذا كنا نقول")
    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "summary"
    assert user_turn in result["text"]


def test_general_scope_does_not_inject_project_knowledge(monkeypatch):
    manager, calls = _manager(monkeypatch)
    captured = {}

    def fake_prompt(*args, **kwargs):
        captured.update(kwargs)
        return "عام", "سياق عام"

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.build_chat_prompt",
        fake_prompt,
    )
    # This assertion targets prompt routing, not the optional local social
    # one-liner used for some correction phrases.
    monkeypatch.setattr(
        ConversationManager,
        "_local_social_answer",
        staticmethod(lambda *_args, **_kwargs: None),
    )
    manager.process(
        "نحن في محادثة ودية عامة ولا نتحدث عن مشروع cyberlab_agent بل عن الذكاء الصناعي"
    )
    assert captured["project_scope"] == "general"
    assert captured["project_knowledge"] is None
    assert captured["agent_self_knowledge"] is None
    assert len(calls) == 1

def test_social_opening_uses_dialogue_history_instead_of_one_generic_template(monkeypatch):
    manager, calls = _manager(monkeypatch)
    first = manager.process("أريد الحديث عن الفن التجريدي")
    assert first["status"] == "success"
    assert first["source"] == "llm"

    result = manager.process("دعنا نتحدث قليلا")

    assert result["status"] == "success"
    assert result["source"] == "local_social_engine"
    assert "الفن التجريدي" in result["text"] or "أريد الحديث عن الفن التجريدي" in result["text"]
    assert len(calls) == 1, "a bounded social opening with available history should be handled locally"


def test_provider_failure_uses_contextual_local_continuation(monkeypatch):
    manager, calls = _manager(monkeypatch)
    first = manager.process("فقط اريد الدردشة معك")
    assert first["status"] == "success"
    assert first["source"] == "llm"

    def unavailable(*_args, **_kwargs):
        return {
            "status": "error",
            "message": "offline",
            "error": {"code": "NO_PROVIDER_AVAILABLE"},
        }

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        unavailable,
    )
    result = manager.process(
        "نعم سنكمل حوارنا في محادثة ودية كنا نقول ونريد ان ندردش قليلا"
    )

    assert result["status"] == "success"
    assert result["source"] == "local_dialogue_fallback"
    assert "فقط اريد الدردشة معك" in result["text"]
    assert "رد سياقي رقم 1" in result["text"]
    assert "متابعة محلية" in result["text"]
    assert calls, "the first turn should have used the configured provider"
