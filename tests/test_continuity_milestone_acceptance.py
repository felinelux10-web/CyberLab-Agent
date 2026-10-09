from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **_kwargs):
        self.calls.append((text, dict(parsed or {})))
        return {"status": "success", "intent": (parsed or {}).get("intent"), "text": "تم"}


def _manager(monkeypatch):
    monkeypatch.setattr(conversation_module, "gateway_ask", lambda *_a, **_k: {
        "status": "success", "text": "إجابة محادثية.", "provider_used": "offline-test",
    })
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(ContextStore())
    return ConversationManager(orchestrator, memory), memory, orchestrator


def test_return_without_previous_topic_is_explicit_and_safe(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    result = manager.process("ارجع للموضوع الرئيسي")
    assert result["semantic_request"]["conversation_act"] == "TOPIC_RETURN"
    assert result["semantic_request"]["context_transition"] == "ambiguous"
    assert result["semantic_request"]["target"] in ("", None)
    assert memory.last_topic in ("", None)
    assert orchestrator.calls == []


def test_named_return_and_continuation_preserve_separate_branches(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")
    manager.process("اشرح CSRF")
    named = manager.process("ارجع لشرح SQL Injection")
    assert named["semantic_request"]["conversation_act"] == "TOPIC_RETURN"
    assert named["semantic_request"]["target"] == "SQL Injection"
    assert memory.last_topic == "SQL Injection"
    assert memory.previous_context_entity()["entity"] == "CSRF"

    continued = manager.process("اكمل الشرح")
    assert continued["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert continued["semantic_request"]["target"] == "SQL Injection"
    assert len(orchestrator.calls) == 4
