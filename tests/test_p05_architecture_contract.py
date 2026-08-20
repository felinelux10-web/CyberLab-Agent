"""
P05 — Architecture/Ownership Contract Tests.

These tests verify boundaries, not implementation details.
"""

from pathlib import Path

from lab_v4_dev.conversation.dialogue_contract import DialogueState
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.conversation_manager import ConversationManager


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None):
        self.calls.append((text, parsed))
        return {
            "status": "success",
            "text": "شرح تجريبي",
            "intent": "explain",
            "target": "orchestrator.py",
            "confidence": 0.9,
        }


class FakeDNI:
    def __init__(self):
        self.calls = []

    def set_conversation_analysis(self, value):
        self.calls.append(value)


def test_dialogue_state_is_conversation_owned():
    state = DialogueState()

    assert hasattr(state, "last_topic")
    assert hasattr(state, "pending_topic")
    assert hasattr(state, "turns")
    assert hasattr(state, "last_items")


def test_dialogue_memory_has_single_state_owner():
    memory = DialogueMemory(object())

    assert isinstance(memory.state, DialogueState)

    memory.last_topic = "orchestrator.py"

    assert memory.state.last_topic == "orchestrator.py"


def test_conversation_manager_does_not_require_dni_for_dialogue_state():
    memory = DialogueMemory(object())
    manager = ConversationManager(
        FakeOrchestrator(),
        dialogue_memory=memory,
        dni=None,
    )

    manager.process("ما وظيفة orchestrator.py؟")

    assert memory.state.last_topic == "orchestrator.py"
    assert len(memory.state.turns) >= 2


def test_dni_receives_analysis_but_does_not_own_dialogue_state():
    memory = DialogueMemory(object())
    dni = FakeDNI()

    manager = ConversationManager(
        FakeOrchestrator(),
        dialogue_memory=memory,
        dni=dni,
    )

    manager.process("ما وظيفة orchestrator.py؟")

    assert dni.calls
    assert memory.state.last_topic == "orchestrator.py"

    # DNI receives analysis metadata only.
    analysis = dni.calls[-1]
    assert "intent" in analysis
    assert "mode" in analysis
    assert "confidence" in analysis
    assert "last_topic" not in analysis
    assert "pending_topic" not in analysis


def test_dialogue_history_is_bounded():
    memory = DialogueMemory(object())

    for i in range(20):
        memory.update(
            f"رسالة {i}",
            {
                "text": f"رد {i}",
                "intent": "question",
                "target": "x.py",
                "confidence": 0.8,
            },
            mode="QUESTION",
        )

    assert len(memory.state.turns) == 8


def test_dialogue_contract_has_no_execution_symbols():
    source = Path(
        "lab_v4_dev/conversation/dialogue_contract.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "subprocess",
        "gateway_ask",
        "orchestrator.handle",
        "execute(",
    )

    for symbol in forbidden:
        assert symbol not in source
