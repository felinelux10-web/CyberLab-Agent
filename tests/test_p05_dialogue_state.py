"""
P05 — Dialogue State / Conversation Lifecycle tests.
"""

from lab_v4_dev.conversation.dialogue_contract import (
    DialogueState,
    DialogueTurn,
)
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class DummyContext:
    pass


def test_dialogue_state_turns_are_bounded():
    state = DialogueState()

    for i in range(12):
        state.add_turn(
            role="user",
            content=f"message-{i}",
            mode="NORMAL",
            intent="question",
            target="x.py",
            confidence=0.9,
        )

    assert len(state.turns) == 8
    assert state.turns[0].content == "message-4"
    assert state.turns[-1].content == "message-11"


def test_dialogue_turn_serialization():
    turn = DialogueTurn(
        role="user",
        content="ما وظيفته؟",
        mode="FOLLOW_UP",
        intent="explain",
        target="orchestrator.py",
        confidence=0.95,
    )

    data = turn.to_dict()

    assert data["role"] == "user"
    assert data["content"] == "ما وظيفته؟"
    assert data["mode"] == "FOLLOW_UP"
    assert data["intent"] == "explain"
    assert data["target"] == "orchestrator.py"
    assert data["confidence"] == 0.95


def test_dialogue_memory_tracks_topic_and_history():
    memory = DialogueMemory(DummyContext())

    memory.update(
        "ما وظيفة orchestrator.py؟",
        {
            "text": "شرح",
            "intent": "explain",
            "target": "orchestrator.py",
            "confidence": 0.9,
        },
        mode="NORMAL",
    )

    assert memory.last_topic == "orchestrator.py"
    assert len(memory.last_list) == 2
    assert memory.state.last_intent == "explain"
    assert memory.state.last_target == "orchestrator.py"


def test_follow_up_does_not_replace_active_topic():
    memory = DialogueMemory(DummyContext())

    memory.update(
        "ما وظيفة orchestrator.py؟",
        {
            "text": "شرح",
            "intent": "explain",
            "target": "orchestrator.py",
            "confidence": 0.9,
        },
        mode="NORMAL",
    )

    memory.update(
        "ما دوره في المشروع؟",
        {
            "text": "شرح الدور",
            "intent": "explain",
            "target": "orchestrator.py",
            "confidence": 0.9,
        },
        mode="FOLLOW_UP",
    )

    assert memory.last_topic == "orchestrator.py"


def test_pronoun_resolution_uses_active_topic():
    memory = DialogueMemory(DummyContext())

    memory.last_topic = "orchestrator.py"

    assert (
        memory.resolve_references("ما دوره في المشروع؟")
        == "orchestrator.py ما دوره في المشروع؟"
    )

    assert (
        memory.resolve_references("لماذا؟")
        == "orchestrator.py لماذا؟"
    )


def test_pending_topic_has_explicit_lifecycle():
    memory = DialogueMemory(DummyContext())

    memory.save_pending("cleaner.py")

    assert memory.state.pending_topic == "cleaner.py"
    assert memory.restore_pending() == "cleaner.py"
    assert memory.state.pending_topic is None


def test_snapshot_is_read_only_representation():
    memory = DialogueMemory(DummyContext())
    memory.last_topic = "state.py"
    memory.last_items = ["state.py", "cleaner.py"]

    snapshot = memory.snapshot()

    assert snapshot["last_topic"] == "state.py"
    assert snapshot["last_items"] == ["state.py", "cleaner.py"]
    assert snapshot["messages"] == 0
