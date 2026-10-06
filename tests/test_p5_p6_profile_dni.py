from pathlib import Path


def test_profile_contains_separate_user_policies_without_dialogue_or_project_state():
    from lab_v4_dev.user_data.profile_loader import load_profile

    profile = load_profile()
    assert profile["explanation_style"]["language"] == "arabic_simple"
    assert profile["engineering_style"]["analyze_before_modify"] is True
    assert profile["trust_policy"]["allow_guessing"] is False
    assert "dialogue_state" not in profile
    assert "project_knowledge" not in profile
    assert "history" not in profile


def test_dni_keeps_reference_to_conversation_owner_without_owning_state():
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.dni.dni_core import DNICore

    memory = DialogueMemory(ContextStore())
    memory.state.last_topic = "SQL Injection"
    memory.state.pending_topic = "CSRF"
    memory.state.add_turn(role="user", content="اشرح SQL Injection")
    memory.state.add_turn(role="assistant", content="شرح مختصر")

    dni = DNICore()
    assert dni.attach_dialogue_memory(memory) is True
    assert dni.has_dialogue_memory() is True
    assert dni.get_dialogue_memory() is memory
    assert dni.get_last_message() == {"role": "assistant", "content": "شرح مختصر"}
    snapshot = dni.conversation_snapshot()
    assert snapshot["attached"] is True
    assert snapshot["last_topic"] == "SQL Injection"
    assert snapshot["pending_topic"] == "CSRF"
    assert snapshot["messages"] == 2
    assert dni.status()["profile_loaded"] is False

    memory.state.last_topic = "CSRF"
    assert dni.conversation_snapshot()["last_topic"] == "CSRF"
