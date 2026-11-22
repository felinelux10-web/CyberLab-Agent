from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class RecordingOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {
            "status": "needs_clarification",
            "intent": (parsed or {}).get("intent"),
            "text": "ما الموضوع الذي تريد شرحه؟",
        }


def test_reference_only_explanation_is_terminal_clarify_and_never_dispatches(monkeypatch):
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    dispatch_calls = []
    original_dispatch = manager._dispatch

    def record_dispatch(*args, **kwargs):
        dispatch_calls.append((args, kwargs))
        return original_dispatch(*args, **kwargs)

    monkeypatch.setattr(manager, "_dispatch", record_dispatch)
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ambiguous reference must not call a provider")
        ),
    )

    result = manager.process("اشرح هذا الأمر")

    assert result["status"] == "needs_clarification"
    assert result["route_decision"].route == "CLARIFY"
    assert result["source"] == "route_clarification"
    assert dispatch_calls == []
    assert orchestrator.calls == []
