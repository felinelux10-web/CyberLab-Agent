from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent import llm_intent_resolver
from lab_v4_dev.nlu import context_resolver


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None):
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
    monkeypatch.setattr(
        manager,
        "_handle_chat",
        lambda text, mode, **_kwargs: {
            "status": "unexpected_chat",
            "text": f"unexpected chat route: {mode} {text}",
        },
    )

    manager.process("اشرح SQL Injection")
    assert memory.last_topic == "SQL Injection"

    manager.process("بسط الشرح اكثر")
    manager.process("اشرح اكثر")

    assert orchestrator.calls[1][0] == "SQL Injection بسط الشرح اكثر"
    assert orchestrator.calls[2][0] == "SQL Injection اشرح اكثر"
    assert [call[1]["target"] for call in orchestrator.calls[:3]] == [
        "SQL Injection",
        "SQL Injection",
        "SQL Injection",
    ]
    assert memory.last_topic == "SQL Injection"

    manager.process("اشرح CSRF")

    assert orchestrator.calls[3][0] == "اشرح CSRF"
    assert orchestrator.calls[3][1]["target"] == "CSRF"
    assert memory.last_topic == "CSRF"
