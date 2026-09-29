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
    monkeypatch.setattr(
        manager,
        "_handle_chat",
        lambda _text, _mode: {
            "status": "unexpected_chat",
            "text": "unexpected chat route",
        },
    )
    return manager, memory, orchestrator


def test_g03_references_stay_on_csrf_despite_stale_nlu_entity(monkeypatch):
    manager, memory, orchestrator = build_manager(monkeypatch)
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
        "CSRF لماذا؟",
        "اشرح لي CSRF بشكل أبسط",
        "ما المقصود بCSRF؟",
    ]
    assert [call[1]["target"] for call in orchestrator.calls] == ["CSRF"] * 6
    assert memory.last_topic == "CSRF"


def test_g03_explicit_topic_switch_becomes_reference_authority(monkeypatch):
    manager, memory, orchestrator = build_manager(monkeypatch)

    manager.process("اشرح CSRF")
    manager.process("اشرح SQL Injection")
    manager.process("اشرح لي هذا بشكل أبسط")

    assert orchestrator.calls[1][0] == "اشرح SQL Injection"
    assert orchestrator.calls[2][0] == "اشرح لي SQL Injection بشكل أبسط"
    assert orchestrator.calls[2][1]["target"] == "SQL Injection"
    assert memory.last_topic == "SQL Injection"


def test_g03_reference_classifier_does_not_capture_explicit_noun():
    from lab_v4_dev.conversation.mode_detector import detect_mode

    assert detect_mode("اشرح هذا الملف") == "QUESTION"
