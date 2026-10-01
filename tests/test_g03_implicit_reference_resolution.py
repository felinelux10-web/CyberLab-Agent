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


def build_manager(monkeypatch):
    # Simulate a stale, unrelated NLU entity. Explicit current-topic
    # references must be resolved before this cache can supply a target.
    stale_entity = {
        "action": "cyber_explain",
        "entity": "SQL Injection",
        "entity_type": "CONCEPT",
        "timestamp": 1_790_665_000,
    }
    monkeypatch.setattr(context_resolver, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(context_resolver, "get_last_entity", lambda: stale_entity)
    monkeypatch.setattr(llm_intent_resolver, "resolve", lambda _text: "unclear")

    memory = DialogueMemory(object())
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(orchestrator, memory)
    return manager, memory, orchestrator


def test_g03_references_stay_on_csrf_despite_stale_nlu_entity(monkeypatch):
    manager, memory, orchestrator = build_manager(monkeypatch)
    gateway_calls = []
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda prompt, **kwargs: (
            gateway_calls.append((prompt, kwargs))
            or {"status": "success", "text": "شرح مبسط.", "provider_used": "test"}
        ),
    )
    sequence = [
        "اشرح CSRF",
        "ما دوره؟",
        "كيف يعمل؟",
        "ولماذا؟",
        "اشرح لي هذا بشكل أبسط",
        "ما المقصود بهذا؟",
    ]

    for text in sequence:
        manager.process(text)

    assert [call[0] for call in orchestrator.calls] == [
        "اشرح CSRF",
        "CSRF ما دوره؟",
        "CSRF كيف يعمل؟",
        "CSRF ولماذا؟",
        "CSRF ما المقصود بهذا؟",
    ]
    assert [call[1]["target"] for call in orchestrator.calls] == ["CSRF"] * 5
    assert len(gateway_calls) == 1
    assert "CSRF" in gateway_calls[0][0]
    assert "لغة مبسطة" in gateway_calls[0][1]["system"]
    assert memory.last_topic == "CSRF"


def test_g03_explicit_topic_switch_becomes_reference_authority(monkeypatch):
    manager, memory, orchestrator = build_manager(monkeypatch)
    gateway_calls = []
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda prompt, **kwargs: (
            gateway_calls.append((prompt, kwargs))
            or {"status": "success", "text": "شرح مبسط.", "provider_used": "test"}
        ),
    )

    manager.process("اشرح CSRF")
    manager.process("اشرح SQL Injection")
    manager.process("اشرح لي هذا بشكل أبسط")

    assert orchestrator.calls[1][0] == "اشرح SQL Injection"
    assert len(orchestrator.calls) == 2
    assert "SQL Injection" in gateway_calls[0][0]
    assert "لغة مبسطة" in gateway_calls[0][1]["system"]
    assert memory.last_topic == "SQL Injection"


def test_g03_reference_classifier_does_not_capture_explicit_noun():
    from lab_v4_dev.conversation.mode_detector import detect_mode

    assert detect_mode("اشرح هذا الملف") == "QUESTION"
