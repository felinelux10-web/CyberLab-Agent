from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent.intent_parser import parse


def test_memory_search_language_is_classified_as_dialogue_history():
    parsed = parse("ابحث جيدا في الذاكرة")
    assert parsed["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert getattr(parsed["intent"], "value", parsed["intent"]) == "personal_chat"
    assert parsed["response_attributes"]["dialogue_response_mode"] == "summary"


def test_memory_search_does_not_call_project_orchestrator(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as module

    project_retrieval = []
    monkeypatch.setattr(
        module,
        "retrieve_for_question",
        lambda question: project_retrieval.append(question),
    )
    calls = []

    class FakeOrchestrator:
        context = ContextStore()

        def handle(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("dialogue memory search must not reach project orchestrator")

    memory = DialogueMemory(ContextStore())
    sid = memory.state.session_id
    memory.state.last_topic = "الفن والرسم"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "تحدثنا عن الفن والرسم",
            "assistant": "توقفنا عند النحت البارز",
            "target": "الفن والرسم",
            "intent": "personal_chat",
            "context_kind": "dialogue",
            "conversation_domain": "general",
        }
    ]
    result = ConversationManager(FakeOrchestrator(), memory).process(
        "ابحث جيدا في الذاكرة"
    )

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert "الفن والرسم" in result["text"]
    assert calls == []
    assert project_retrieval == []


def test_project_file_wording_remains_outside_dialogue_memory():
    parsed = parse("ابحث في ملفات المشروع عن conversation_manager.py")
    assert parsed["conversation_act"] != "CONVERSATION_HISTORY_QUERY"
    assert parsed["conversation_domain"] == "project"
