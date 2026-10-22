from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class RecordingOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {
            "status": "success",
            "intent": (parsed or {}).get("intent"),
            "text": "رد تنفيذ غير متوقع",
        }


def make_manager(monkeypatch):
    calls = []

    def gateway(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": "رد حواري عن الموضوع الحالي",
            "provider_used": "test",
        }

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        gateway,
    )
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    return ConversationManager(orchestrator, memory), memory, orchestrator, calls


def test_film_topic_and_latest_film_question_stay_in_dialogue(monkeypatch):
    manager, memory, orchestrator, calls = make_manager(monkeypatch)

    opened = manager.process("مثلا عن الافلام الاكشن والغموض")
    latest = manager.process("ماهي احدث افلام مثل هذه السلسلة")

    assert opened["intent"] == "personal_chat"
    assert memory.state.last_topic == "الافلام الاكشن والغموض"
    assert latest["source"] == "llm"
    assert latest["intent"] == "personal_chat"
    assert "save_prompt" not in latest
    assert orchestrator.calls == []
    assert len(calls) == 2


def test_film_dialogue_acknowledgement_and_current_dialogue_keep_active_branch(monkeypatch):
    manager, memory, orchestrator, calls = make_manager(monkeypatch)
    manager.process("مثلا عن الافلام الاكشن والغموض")

    for phrase in ("نعم صحيح نكمل", "انا اقول الحوار الحالي"):
        result = manager.process(phrase)
        assert result["source"] == "llm"
        assert result["intent"] == "personal_chat"
        assert result["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
        assert "استكمال الحوار السابق أم استكمال العمل" not in result["text"]
        assert "save_prompt" not in result

    assert memory.state.last_topic == "الافلام الاكشن والغموض"
    assert orchestrator.calls == []
    assert len(calls) == 3


def test_summary_is_owned_by_dialogue_memory_and_does_not_create_a_new_topic(monkeypatch):
    manager, memory, orchestrator, calls = make_manager(monkeypatch)
    manager.process("مثلا عن الافلام الاكشن والغموض")
    before = memory.state.last_topic

    result = manager.process("اكتب ملخص")

    assert result["source"] == "dialogue_memory"
    assert result["intent"] == "memory_dump"
    assert "الافلام الاكشن والغموض" in result["text"]
    assert memory.state.last_topic == before
    assert orchestrator.calls == []
    assert len(calls) == 1


def test_art_follow_up_cannot_become_sql_or_cyber_explanation(monkeypatch):
    manager, memory, orchestrator, calls = make_manager(monkeypatch)
    manager.process("موضوع الرسم والنحت والنقش البارز")

    result = manager.process("جيد جدا اكمل الشرح اكثر")

    assert result["source"] == "llm"
    assert result["intent"] == "personal_chat"
    assert result["semantic_request"]["target"] == "الرسم والنحت والنقش البارز"
    assert result["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert "SQL" not in result["text"]
    assert orchestrator.calls == []
    assert len(calls) == 2
