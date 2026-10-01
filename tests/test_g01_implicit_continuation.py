from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent import llm_intent_resolver
from lab_v4_dev.nlu import context_resolver


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
            "text": "deterministic response",
            "source": "test",
        }


def test_implicit_explanation_continuation_preserves_topic_and_explicit_switch(monkeypatch):
    # Keep the canonical parser enabled, but make its optional state/LLM
    # fallbacks deterministic and side-effect free for this regression.
    monkeypatch.setattr(context_resolver, "save_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(context_resolver, "get_last_entity", lambda: {})
    monkeypatch.setattr(llm_intent_resolver, "resolve", lambda _text: "unclear")

    memory = DialogueMemory(object())
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(orchestrator, memory)
    gateway_calls = []
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda prompt, **kwargs: (
            gateway_calls.append((prompt, kwargs))
            or {"status": "success", "text": "شرح مبسط.", "provider_used": "test"}
        ),
    )

    manager.process("اشرح SQL Injection")
    assert memory.last_topic == "SQL Injection"

    manager.process("بسط الشرح اكثر")
    manager.process("اشرح اكثر")

    assert len(gateway_calls) == 1
    assert "SQL Injection" in gateway_calls[0][0]
    assert "لغة مبسطة" in gateway_calls[0][1]["system"]
    assert orchestrator.calls[1][0] == "SQL Injection اشرح اكثر"
    assert [call[1]["target"] for call in orchestrator.calls[:2]] == [
        "SQL Injection",
        "SQL Injection",
    ]
    assert memory.last_topic == "SQL Injection"

    manager.process("اشرح CSRF")

    assert orchestrator.calls[2][0] == "اشرح CSRF"
    assert orchestrator.calls[2][1]["target"] == "CSRF"
    assert memory.last_topic == "CSRF"
