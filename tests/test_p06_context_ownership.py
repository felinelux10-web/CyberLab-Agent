
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


def test_dialogue_memory_uses_supplied_canonical_context():
    context = ContextStore()
    memory = DialogueMemory(context)

    assert memory.context is context


def test_dialogue_memory_owns_dialogue_state():
    context = ContextStore()
    memory = DialogueMemory(context)

    assert memory.state is not None
    assert memory.last_topic is None
    assert memory.pending_topic is None
    assert memory.last_list == []
    assert memory.last_items == []


def test_dialogue_memory_reset_does_not_replace_context_owner():
    context = ContextStore()
    memory = DialogueMemory(context)

    memory.last_topic = "orchestrator.py"
    memory.pending_topic = "previous"

    memory.reset()

    assert memory.context is context
    assert memory.last_topic is None
    assert memory.pending_topic is None
    assert memory.last_list == []
    assert memory.last_items == []


def test_agent_context_and_dialogue_memory_share_context():
    from lab_v4_dev.core.agent import Agent

    agent = Agent()
    assert agent.boot() is True

    assert agent.context is agent.orchestrator.context
    assert agent.dialogue_memory.context is agent.context


def test_agent_conversation_reset():
    from lab_v4_dev.core.agent import Agent

    agent = Agent()
    assert agent.boot() is True

    agent.context.last_intent = "analyze_code"
    agent.context.last_target = "orchestrator.py"
    agent.context.last_result = {"status": "success"}

    if hasattr(agent.context, "current_subject"):
        agent.context.current_subject = "orchestrator.py"
    if hasattr(agent.context, "current_version"):
        agent.context.current_version = "v5"
    if hasattr(agent.context, "current_file"):
        agent.context.current_file = "orchestrator.py"
    if hasattr(agent.context, "current_analysis"):
        agent.context.current_analysis = "analysis"

    agent.dialogue_memory.last_topic = "orchestrator.py"
    agent.dialogue_memory.pending_topic = "previous"

    agent.reset_conversation_context()

    assert agent.context.last_intent is None
    assert agent.context.last_target is None
    assert agent.context.last_result is None

    if hasattr(agent.context, "current_subject"):
        assert agent.context.current_subject is None
    if hasattr(agent.context, "current_version"):
        assert agent.context.current_version is None
    if hasattr(agent.context, "current_file"):
        assert agent.context.current_file is None
    if hasattr(agent.context, "current_analysis"):
        assert agent.context.current_analysis is None

    assert agent.dialogue_memory.last_topic is None
    assert agent.dialogue_memory.pending_topic is None
    assert agent.dialogue_memory.last_list == []
    assert agent.dialogue_memory.last_items == []
