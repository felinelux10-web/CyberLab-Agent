from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent.intent_parser import parse


def test_shortening_request_preserves_style_metadata():
    parsed = parse("اختصر أكثر")
    assert parsed["conversation_act"] == "VERBOSITY_REQUEST"
    assert parsed["response_attributes"]["verbosity"] == "concise"


def test_shortening_restored_dialogue_uses_saved_branch_and_concise_style(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as module

    calls = []
    monkeypatch.setattr(
        module,
        "gateway_ask",
        lambda prompt, **kwargs: calls.append((prompt, kwargs)) or {
            "status": "success",
            "text": "الفن والرسم موضوعان بصريان؛ توقفنا عند النحت البارز.",
            "provider_used": "test",
        },
    )
    context = ContextStore()
    memory = DialogueMemory(context)
    memory.restore_snapshot(
        {
            "session_id": "saved-concise-1",
            "last_topic": "الفن والرسم",
            "last_intent": "personal_chat",
            "last_entity_type": "CONCEPT",
            "exchange_archive": [
                {
                    "session_id": "saved-concise-1",
                    "user": "ناقشنا الفن والرسم",
                    "assistant": "توقفنا عند النحت البارز",
                    "target": "الفن والرسم",
                    "intent": "personal_chat",
                    "context_kind": "dialogue",
                    "conversation_domain": "general",
                }
            ],
            "history": [],
        }
    )
    manager = ConversationManager(SimpleNamespace(context=context), memory)

    result = manager.process("اختصر أكثر")

    assert result["status"] == "success"
    assert result["semantic_request"]["conversation_act"] == "VERBOSITY_REQUEST"
    assert result["semantic_request"]["context_transition"] == "continue"
    assert result["semantic_request"]["target"] == "الفن والرسم"
    assert result["semantic_request"]["response_attributes"]["verbosity"] == "concise"
    assert calls
    assert "ناقشنا الفن والرسم" in calls[-1][0]
    assert "توقفنا عند النحت البارز" in calls[-1][0]
    assert "مختصر" in calls[-1][1]["system"] or "موجز" in calls[-1][1]["system"]
