from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


def test_restore_snapshot_marks_selected_dialogue_as_active_owner():
    memory = DialogueMemory(ContextStore())
    assert memory.restore_snapshot(
        {
            "session_id": "saved-dialogue-42",
            "last_topic": "الفن والرسم",
            "last_intent": "personal_chat",
            "exchange_archive": [
                {
                    "session_id": "saved-dialogue-42",
                    "user": "ناقشنا الفن والرسم",
                    "assistant": "توقفنا عند الرسم والنحت",
                    "target": "الفن والرسم",
                    "intent": "personal_chat",
                    "context_kind": "dialogue",
                    "conversation_domain": "general",
                }
            ],
            "history": [],
        }
    ) is True

    assert memory.active_restored_session() == {
        "session_id": "saved-dialogue-42",
        "topic": "الفن والرسم",
    }
    assert memory.active_context_entity()["entity"] == "الفن والرسم"
    assert memory.snapshot()["active_restored_session_id"] == "saved-dialogue-42"


def test_follow_up_after_restore_uses_restored_topic(monkeypatch):
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda prompt, **kwargs: {
            "status": "success",
            "text": "نكمل من النقطة المحفوظة.",
            "provider_used": "test",
        },
    )
    context = ContextStore()
    memory = DialogueMemory(context)
    memory.restore_snapshot(
        {
            "session_id": "saved-dialogue-43",
            "last_topic": "النحت البارز",
            "last_intent": "personal_chat",
            "exchange_archive": [
                {
                    "session_id": "saved-dialogue-43",
                    "user": "توقفنا عند النحت البارز",
                    "assistant": "وصلنا إلى المثال الثاني.",
                    "target": "النحت البارز",
                    "intent": "personal_chat",
                    "context_kind": "dialogue",
                    "conversation_domain": "general",
                }
            ],
            "history": [],
        }
    )
    manager = ConversationManager(
        SimpleNamespace(context=context),
        memory,
    )

    result = manager.process("أكمل")

    assert result["status"] == "success"
    assert result["semantic_request"]["target"] == "النحت البارز"
    assert result["semantic_request"]["context_transition"] == "continue"
    assert memory.active_restored_session()["session_id"] == "saved-dialogue-43"


def test_reset_closes_restored_session_reference():
    memory = DialogueMemory(ContextStore())
    memory.restore_snapshot({"session_id": "saved-dialogue-44", "last_topic": "موضوع محفوظ"})
    memory.reset()
    assert memory.active_restored_session() is None
