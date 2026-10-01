from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent.intents import Intent


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **_kwargs):
        parsed = dict(parsed or {})
        self.calls.append((text, parsed))
        if parsed.get("intent") == Intent.CYBER_EXPLAIN and not parsed.get("target"):
            return {
                "status": "needs_clarification",
                "intent": parsed.get("intent"),
                "text": "ما الموضوع الذي تريد شرحه؟",
                "source": "test",
            }
        return {
            "status": "success",
            "intent": parsed.get("intent"),
            "target": parsed.get("target"),
            "text": "deterministic response",
            "source": "test",
        }


def semantic_result(intent, target="", entity_type="UNKNOWN"):
    return {
        "intent": intent,
        "target": target,
        "context": "",
        "confidence": 0.9,
        "entity_type": entity_type,
        "semantic_pattern": "",
    }


def test_chat_turn_reuses_the_single_canonical_parse(monkeypatch):
    parse_calls = []
    gateway_calls = []

    def canonical_parse(text, **_kwargs):
        parse_calls.append(text)
        return semantic_result(Intent.PERSONAL_CHAT)

    monkeypatch.setattr(conversation_module, "parse", canonical_parse)
    monkeypatch.setattr(conversation_module, "detect_mode", lambda _text: "CHAT")
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda prompt, **kwargs: (
            gateway_calls.append((prompt, kwargs))
            or {"status": "success", "text": "أهلًا بك.", "provider_used": "test"}
        ),
    )
    manager = ConversationManager(RecordingOrchestrator(), DialogueMemory(object()))

    result = manager.process("مرحبا")

    assert parse_calls == ["مرحبا"]
    assert result["source"] == "llm"
    assert len(gateway_calls) == 1
    assert result["intent"] == Intent.PERSONAL_CHAT


def test_second_parse_is_only_for_explicit_contextual_reresolution(monkeypatch):
    parse_calls = []

    def canonical_parse(text, **kwargs):
        parse_calls.append((text, kwargs.get("context_entity")))
        if text == "اشرح SQL Injection":
            return semantic_result(Intent.CYBER_EXPLAIN, "SQL Injection", "CONCEPT")
        if text == "اشرح اكثر":
            return semantic_result(Intent.CYBER_EXPLAIN, "", "ELABORATION")
        if text == "SQL Injection اشرح اكثر":
            return semantic_result(Intent.CYBER_EXPLAIN, "SQL Injection", "CONCEPT")
        raise AssertionError(f"unexpected parse input: {text}")

    monkeypatch.setattr(conversation_module, "parse", canonical_parse)
    manager = ConversationManager(RecordingOrchestrator(), DialogueMemory(object()))

    manager.process("اشرح SQL Injection")
    manager.process("اشرح اكثر")

    assert [text for text, _context in parse_calls] == [
        "اشرح SQL Injection",
        "اشرح اكثر",
        "SQL Injection اشرح اكثر",
    ]
    assert parse_calls[1][1] is None
    assert parse_calls[2][1] == {
        "action": Intent.CYBER_EXPLAIN,
        "entity": "SQL Injection",
        "entity_type": "CONCEPT",
    }


def test_compatibility_handlers_delegate_to_process(monkeypatch):
    manager = ConversationManager(RecordingOrchestrator())
    calls = []

    def canonical_process(text):
        calls.append(text)
        return {"status": "canonical", "text": text}

    monkeypatch.setattr(manager, "process", canonical_process)

    for handler_name in ("_handle_task", "_handle_system", "_handle_follow_up"):
        result = getattr(manager, handler_name)("sample request")
        assert result == {"status": "canonical", "text": "sample request"}

    assert calls == ["sample request"] * 3


def test_independent_topic_without_valid_entity_cannot_authorize_followup(monkeypatch):
    parse_calls = []

    def canonical_parse(text, **_kwargs):
        parse_calls.append(text)
        if text == "اشرح SQL Injection":
            return semantic_result(Intent.CYBER_EXPLAIN, "SQL Injection", "CONCEPT")
        if text == "ما هي أهمية التعلم المستمر؟":
            return semantic_result(
                Intent.PERSONAL_CHAT,
                "أهمية التعلم المستمر",
                "UNKNOWN",
            )
        if text == "اشرح":
            return semantic_result(Intent.CYBER_EXPLAIN, "", "ELABORATION")
        raise AssertionError(f"unexpected parse input: {text}")

    real_detect_mode = conversation_module.detect_mode

    def deterministic_mode(text):
        if text == "اشرح":
            return "FOLLOW_UP"
        if text == "ما هي أهمية التعلم المستمر؟":
            return "QUESTION"
        return real_detect_mode(text)

    monkeypatch.setattr(conversation_module, "parse", canonical_parse)
    monkeypatch.setattr(conversation_module, "detect_mode", deterministic_mode)
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda _prompt, **_kwargs: {
            "status": "success",
            "text": "إجابة عامة.",
            "provider_used": "offline-test",
        },
    )

    memory = DialogueMemory(object())
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    manager.process("ما هي أهمية التعلم المستمر؟")
    assert memory.last_topic == "أهمية التعلم المستمر"
    assert memory.state.last_entity_type == "UNKNOWN"
    assert memory.active_context_entity() is None

    result = manager.process("اشرح")

    assert result["status"] == "needs_clarification"
    assert result["semantic_request"]["context_transition"] == "ambiguous"
    assert orchestrator.calls[-1][0] == "اشرح"
    assert orchestrator.calls[-1][1]["target"] == ""
    assert parse_calls.count("اشرح") == 1
    assert "أهمية التعلم المستمر اشرح" not in parse_calls
    assert memory.last_topic == "أهمية التعلم المستمر"
    assert memory.state.last_entity_type == "UNKNOWN"
