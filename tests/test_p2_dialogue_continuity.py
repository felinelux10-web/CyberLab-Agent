from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **_kwargs):
        parsed = dict(parsed or {})
        self.calls.append((text, parsed))
        return {
            "status": "success",
            "intent": parsed.get("intent"),
            "target": parsed.get("target"),
            "text": "إجابة مرتبطة بالموضوع.",
        }


def _manager(monkeypatch):
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda *_a, **_k: {
            "status": "success",
            "text": "إجابة محادثية.",
            "provider_used": "offline-test",
        },
    )
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(ContextStore())
    return ConversationManager(orchestrator, memory), memory, orchestrator


def test_correction_preserves_active_topic(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")
    result = manager.process("لا، ليس هذا ما أقصده")

    assert result["semantic_request"]["conversation_act"] == "CORRECTION"
    assert result["semantic_request"]["context_transition"] == "continue"
    assert result["semantic_request"]["target"] == "SQL Injection"
    assert memory.last_topic == "SQL Injection"
    assert len(orchestrator.calls) == 2


def test_compound_reference_resolves_ordinal_item_without_losing_topic():
    memory = DialogueMemory(ContextStore())
    memory.last_topic = "SQL Injection"
    memory.state.last_entity_type = "CONCEPT"
    memory.last_items = ["السبب الأول", "السبب الثاني"]

    resolved = memory.resolve_references("النقطة الثانية من الشرح")

    assert resolved == "SQL Injection السبب الثاني من الشرح"


def test_topic_return_restores_previous_branch_without_explicit_topic(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")
    manager.process("اشرح CSRF")
    returned = manager.process("ارجع للموضوع الرئيسي")

    assert returned["semantic_request"]["conversation_act"] == "TOPIC_RETURN"
    assert returned["semantic_request"]["context_transition"] == "restore"
    assert returned["semantic_request"]["target"] == "SQL Injection"
    assert memory.last_topic == "SQL Injection"
    assert memory.previous_context_entity()["entity"] == "CSRF"
    assert len(orchestrator.calls) == 3
