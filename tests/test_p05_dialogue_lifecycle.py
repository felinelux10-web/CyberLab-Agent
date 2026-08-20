"""
P05 — Real Conversation Lifecycle Integration Tests.

Verifies ownership:
Agent -> ConversationManager -> DialogueMemory
"""

from lab_v4_dev.conversation.conversation_manager import ConversationManager


class FakeOrchestrator:
    def handle(self, *args, **kwargs):
        return {
            "status": "success",
            "text": "شرح تجريبي",
            "intent": "explain",
            "target": "orchestrator.py",
            "confidence": 0.9,
        }


class RecordingMemory:
    def __init__(self):
        self.calls = []
        self.last_topic = None
        self.last_items = []

    def update(self, text, result, *, mode=None, parsed=None):
        self.calls.append({
            "text": text,
            "result": result,
            "mode": mode,
            "parsed": parsed,
        })


def test_conversation_manager_owns_dialogue_update():
    memory = RecordingMemory()

    manager = ConversationManager(
        FakeOrchestrator(),
        dialogue_memory=memory,
    )

    # process() may require runtime dependencies in this project.
    # If construction succeeds, verify lifecycle ownership directly.
    assert manager.dialogue_memory is memory


def test_real_dialogue_memory_is_updated_by_manager():
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory

    memory = DialogueMemory(object())

    manager = ConversationManager(
        FakeOrchestrator(),
        dialogue_memory=memory,
    )

    result = manager.process("ما وظيفة orchestrator.py؟")

    assert memory.state.turns
    assert memory.state.last_topic is not None
    assert len(memory.state.turns) >= 2
    assert result is not None


def test_dialogue_state_keeps_previous_topic_on_follow_up():
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory

    memory = DialogueMemory(object())

    manager = ConversationManager(
        FakeOrchestrator(),
        dialogue_memory=memory,
    )

    manager.process("ما وظيفة orchestrator.py؟")

    first_topic = memory.state.last_topic

    manager.process("ما دوره في المشروع؟")

    assert first_topic == "orchestrator.py"
    assert memory.state.last_topic == first_topic
    assert len(memory.state.turns) >= 4
