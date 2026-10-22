from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
import lab_v4_dev.conversation.conversation_manager as conversation_module


class RecordingOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {"status": "success", "intent": (parsed or {}).get("intent"), "text": "orchestrator"}


def manager(monkeypatch, response="رد حواري محفوظ"):
    prompts = []

    def gateway(prompt, **kwargs):
        prompts.append(str(prompt))
        return {"status": "success", "text": response, "provider_used": "test"}

    monkeypatch.setattr(conversation_module, "gateway_ask", gateway)
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    return ConversationManager(orchestrator, memory), memory, orchestrator, prompts


def test_dialogue_question_does_not_trigger_diagnostics_but_explicit_health_does(monkeypatch):
    manager_, memory, orchestrator, _ = manager(monkeypatch)
    manager_.process("موضوع الفن التجريدي وتقنيات اللون")

    dialogue = manager_.process("ما الاقتراح الاول؟")
    assert dialogue["intent"] == "personal_chat"
    assert dialogue["executed"] is False
    assert orchestrator.calls == []

    health = manager_.process("هل النظام سليم؟")
    assert health["intent"] == "health"
    assert health["executed"] is True
    assert len(orchestrator.calls) == 1
    assert memory.last_topic == "الفن التجريدي وتقنيات اللون"


def test_capability_question_about_diagnosis_stays_dialogue(monkeypatch):
    manager_, _, orchestrator, _ = manager(monkeypatch)
    manager_.process("موضوع الفن التجريدي")

    result = manager_.process("هل تستطيع تشخيص ذلك؟")

    assert result["intent"] == "personal_chat"
    assert result["executed"] is False
    assert orchestrator.calls == []


def test_creative_continuation_cannot_become_sql_or_lab_plan(monkeypatch):
    manager_, memory, orchestrator, _ = manager(monkeypatch)
    manager_.process("موضوع الفن التجريدي وتقنيات اللون")

    result = manager_.process("اكمل الشرح بدون تغيير الموضوع مع مثال SQL")

    assert result["intent"] == "personal_chat"
    assert result["semantic_request"]["target"] == "الفن التجريدي وتقنيات اللون"
    assert result["semantic_request"]["context_transition"] == "continue"
    assert result["executed"] is False
    assert memory.last_topic == "الفن التجريدي وتقنيات اللون"
    assert orchestrator.calls == []


def test_restore_topic_uses_saved_branch_identity_not_synthetic_parser_text(monkeypatch):
    manager_, memory, orchestrator, prompts = manager(monkeypatch)
    manager_.process("موضوع الفن التجريدي والنقش البارز")
    manager_.switch_topic("الفن التجريدي والنقش البارز", "موضوع الشبكات")

    restored = manager_.restore_topic()

    assert restored["status"] == "success"
    assert restored["semantic_request"]["context_transition"] == "restore"
    assert restored["semantic_request"]["target"] == "الفن التجريدي والنقش البارز"
    assert memory.last_topic == "الفن التجريدي والنقش البارز"
    assert "استعادة الفرع الحواري المحفوظ" in prompts[-1]
    assert "ارجع لشرح" not in prompts[-1]
    assert orchestrator.calls == []


def test_continuation_provider_failure_returns_safe_last_point(monkeypatch):
    manager_, memory, orchestrator, _ = manager(monkeypatch)
    manager_.process("موضوع الفن التجريدي وتقنيات اللون")
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {"status": "error", "error": {"code": "TIMEOUT"}},
    )

    result = manager_.process("اكمل الشرح")

    assert result["status"] == "error"
    assert result["executed"] is False
    assert result["source"] == "fallback"
    assert "آخر نقطة محفوظة" in result["text"]
    assert memory.last_topic == "الفن التجريدي وتقنيات اللون"
    assert orchestrator.calls == []
    assert not any(item.get("assistant") == result["text"] for item in memory.state.exchange_archive)


def test_targetless_deictic_reference_uses_dialogue_branch_without_literal_target(monkeypatch):
    manager_, memory, orchestrator, prompts = manager(monkeypatch)
    manager_.process("أشعر أن الذكاء الاصطناعي يتطور بسرعة")

    result = manager_.process("ماذا يعني هذا")

    assert result["intent"] == "personal_chat"
    assert result["executed"] is False
    assert result["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert result["semantic_request"]["target"] in {None, ""}
    assert "هذا" not in (result["semantic_request"]["target"] or "")
    assert prompts
    assert orchestrator.calls == []
