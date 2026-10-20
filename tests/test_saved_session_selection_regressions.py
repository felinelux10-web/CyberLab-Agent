from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.memory.session_state import session_selector


def test_session_selector_keeps_explicit_number_and_saved_session_list():
    assert session_selector("استرجع الجلسة 3") == {
        "kind": "number", "number": 3, "report_mode": "standard"
    }
    assert session_selector("استرجع سياق حوار الجلسة المحفوظة")["kind"] == "list"


def test_orchestrator_restores_the_selected_number_not_the_latest(monkeypatch):
    sessions = [
        {"session_id": "session-1", "session_type": "dialogue", "status": "completed",
         "active_goal": "الفن", "dialogue_state": {"session_id": "dialogue-1"}},
        {"session_id": "session-2", "session_type": "dialogue", "status": "completed",
         "active_goal": "Python", "dialogue_state": {"session_id": "dialogue-2"}},
        {"session_id": "session-3", "session_type": "work", "status": "paused",
         "active_goal": "عمل آخر", "next_step": "متابعة"},
    ]
    selected = []
    agent = SimpleNamespace(
        restore_session_snapshot=lambda data: selected.append(data) or True,
        restore_session_context=lambda: False,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    orchestrator = Orchestrator(agent)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_index", lambda: sessions)
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_id",
        lambda session_id: next((item for item in sessions if item["session_id"] == session_id), {}),
    )
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: sessions[-1])
    monkeypatch.setattr("lab_v4_dev.memory.session_state.recoverable_work_checkpoint", lambda data: None)

    result = orchestrator.handle(
        "استرجع الجلسة 1",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "system",
            "session_selector": {"kind": "number", "number": 1, "report_mode": "standard"},
        },
    )

    assert result["status"] == "success"
    assert selected and selected[0]["session_id"] == "session-1"
    assert "الفن" in result["text"]


def test_dialogue_topic_survives_example_and_ordinal_return(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda prompt, **kwargs: calls.append(prompt) or {
            "status": "success", "text": "رد حواري", "provider_used": "test"
        },
    )
    manager = ConversationManager(
        SimpleNamespace(context=ContextStore()),
        DialogueMemory(ContextStore()),
    )
    manager.process("عن موضوع الفن")
    manager.process("الرسم والنحت والنقش البارز")
    manager.process("مثلا اعطيني مثال")
    result = manager.process("عن الموضوع الذي كنا نتحدث فيه قبل ردين")

    assert result["status"] == "success"
    assert result.get("source") != "dialogue_memory"
    assert calls
    assert "الرسم والنحت والنقش البارز" in calls[-1]


def test_saved_dialogue_is_not_loaded_implicitly_by_a_new_dialogue_memory():
    memory = DialogueMemory(ContextStore())
    assert memory.state.last_topic is None
    assert memory.state.exchange_archive == []


def test_named_social_switch_and_correction_stay_in_dialogue_route(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda prompt, **kwargs: {"status": "success", "text": "رد حواري", "provider_used": "test"},
    )
    orchestrator = SimpleNamespace(
        context=ContextStore(),
        handle=lambda *args, **kwargs: calls.append(kwargs.get("parsed")) or {
            "status": "success", "text": "ORCHESTRATOR"
        },
    )
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("دعنا نتحدث عن الكتب")
    switched = manager.process("حسنا دعنا ننتقل لكتب علم النفس")
    corrected = manager.process("لا قلت موضوع الكتب الذي كنا نناقشه")
    continued = manager.process("اجل اكمل")

    assert getattr(switched["intent"], "value", switched["intent"]) == "personal_chat"
    assert corrected["source"] != "dialogue_memory"
    assert continued["source"] != "dialogue_memory"
    assert not calls
    assert memory.state.last_topic == "الكتب"
