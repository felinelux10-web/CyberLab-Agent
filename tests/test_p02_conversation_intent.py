from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.semantic_contract import (
    SemanticRequest,
    build_semantic_request,
)
from lab_v4_dev.intent.intent_parser import parse


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None):
        self.calls.append((text, parsed))
        return {
            "status": "success",
            "intent": parsed.get("intent") if parsed else None,
            "text": "ORCHESTRATOR",
            "source": "orchestrator",
        }


class FakeMemory:
    last_list = []

    def resolve_references(self, text):
        return text


def test_p02_semantic_contract_is_existing_contract():
    result = build_semantic_request(
        "اشرح SQL Injection",
        "QUESTION",
        confidence=0.85,
        target=None,
    )

    assert isinstance(result, SemanticRequest)
    assert result.mode == "QUESTION"
    assert result.action_type == "analyze"
    assert result.confidence == 0.85


def test_executable_question_is_owned_by_orchestrator():
    orchestrator = FakeOrchestrator()

    manager = ConversationManager(
        orchestrator=orchestrator,
        dialogue_memory=FakeMemory(),
    )

    result = manager.process("اشرح SQL Injection")

    assert len(orchestrator.calls) == 1
    assert result["source"] == "orchestrator"
    assert result["intent"] == parse("اشرح SQL Injection")["intent"]


def test_executable_follow_up_is_owned_by_orchestrator():
    orchestrator = FakeOrchestrator()

    manager = ConversationManager(
        orchestrator=orchestrator,
        dialogue_memory=FakeMemory(),
    )

    result = manager.process("كيف يعمل؟")

    assert len(orchestrator.calls) == 1
    assert result["source"] == "orchestrator"
    assert result["intent"] == parse("كيف يعمل؟")["intent"]


def test_non_executable_chat_does_not_reach_orchestrator(monkeypatch):
    orchestrator = FakeOrchestrator()

    manager = ConversationManager(
        orchestrator=orchestrator,
        dialogue_memory=FakeMemory(),
    )

    monkeypatch.setattr(
        manager,
        "_handle_chat",
        lambda text, mode: {
            "status": "success",
            "intent": mode.lower(),
            "text": "CHAT",
            "mode": mode,
            "source": "llm",
        },
    )

    result = manager.process("مرحبا")

    assert len(orchestrator.calls) == 0
    assert result["source"] == "llm"


def test_parser_remains_single_semantic_authority():
    parsed = parse("اشرح SQL Injection")

    assert isinstance(parsed, dict)
    assert parsed["intent"] is not None
    assert "target" in parsed
    assert "context" in parsed
