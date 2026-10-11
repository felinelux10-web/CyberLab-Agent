from pathlib import Path


def _isolate_project_data(monkeypatch, tmp_path):
    import lab_v4_dev.core.project_context as context
    from lab_v4_dev.awareness import project_knowledge

    project_root = (tmp_path / "project").resolve()
    project_root.mkdir()
    monkeypatch.setattr(
        context,
        "project_index_dir",
        lambda root: str(tmp_path / "indices" / Path(root).name),
    )
    monkeypatch.setattr(
        context,
        "_active_project",
        context.ProjectContext(str(project_root)),
    )
    project_knowledge.invalidate_cache()
    return project_root


def test_dialogue_checkpoint_round_trips_bounded_context():
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory

    original = DialogueMemory(ContextStore())
    original.state.last_topic = "SQL Injection"
    original.state.last_entity_type = "CONCEPT"
    original.state.last_intent = "cyber_explain"
    original.last_items = ["سبب أول", "سبب ثانٍ"]
    original.state.context_history = [{
        "action": "cyber_explain",
        "entity": "CSRF",
        "entity_type": "CONCEPT",
    }]
    original.state.add_turn(
        role="user", content="اشرح SQL Injection", intent="cyber_explain",
        target="SQL Injection", confidence=0.9,
    )
    snapshot = original.snapshot()

    restored = DialogueMemory(ContextStore())
    assert restored.restore_snapshot(snapshot) is True
    assert restored.active_context_entity()["entity"] == "SQL Injection"
    assert restored.last_items == ["سبب أول", "سبب ثانٍ"]
    assert restored.context_for_topic("CSRF")["entity_type"] == "CONCEPT"
    assert restored.last_list[0]["content"] == "اشرح SQL Injection"
    assert len(restored.last_list) <= 8


def test_recoverable_checkpoint_preserves_work_metadata_and_context(monkeypatch, tmp_path):
    project_root = _isolate_project_data(monkeypatch, tmp_path)
    from lab_v4_dev.awareness import project_knowledge
    from lab_v4_dev.memory.session_state import (
        load_session,
        save_recoverable_checkpoint,
    )

    project_knowledge.save_session({
        "active_goal": "هدف محفوظ",
        "completed_work": ["خطوة 1"],
        "decisions": ["قرار سابق"],
    })
    saved = save_recoverable_checkpoint(
        active_goal="شرح SQL Injection",
        next_step="استكمال: SQL Injection",
        dialogue_state={"last_topic": "SQL Injection", "history": []},
        context_state={"subject": "SQL Injection", "file": "main.py"},
        project_root=str(project_root),
        version="test",
    )
    loaded = load_session()

    assert saved["completed_work"] == ["خطوة 1"]
    assert loaded["decisions"] == ["قرار سابق"]
    assert loaded["session_type"] == "work"
    assert "dialogue_state" not in loaded
    assert loaded["context_state"]["file"] == "main.py"
    assert loaded["project_root"] == str(project_root)
    assert loaded["active_goal"] == "شرح SQL Injection"


def test_session_restore_command_reports_recoverable_context(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core import orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.intent.intents import Intent

    restored = []
    monkeypatch.setattr(
        orchestrator_module,
        "Intent",
        Intent,
        raising=False,
    )
    agent = SimpleNamespace(
        restore_session_context=lambda: restored.append(True) or True,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    orchestrator = Orchestrator(agent)
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.load_session",
        lambda: {
            "timestamp": "2026-10-06T12:00:00",
            "active_goal": "شرح SQL Injection",
            "next_step": "استكمال: SQL Injection",
            "last_files": ["main.py"],
            "dialogue_state": {"last_topic": "SQL Injection"},
        },
    )

    result = orchestrator.handle(
        "استكمل الجلسة",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "general",
            "raw": "استكمل الجلسة",
        },
    )

    assert result["status"] == "success"
    assert restored == [True]
    assert "تمت استعادته" in result["text"]



def test_dialogue_checkpoint_is_persisted_separately_from_work(monkeypatch, tmp_path):
    project_root = _isolate_project_data(monkeypatch, tmp_path)
    from lab_v4_dev.memory.session_state import (
        get_latest_session_by_type,
        load_session,
        save_dialogue_checkpoint,
        save_recoverable_checkpoint,
    )

    work = save_recoverable_checkpoint(
        active_goal="إصلاح ملف",
        next_step="استكمال إصلاح الملف",
        context_state={"last_intent": "modify_file", "current_file": "main.py"},
        project_root=str(project_root),
    )
    dialogue = save_dialogue_checkpoint(
        dialogue_state={
            "last_topic": "SQL Injection",
            "history": [
                {"role": "user", "content": "اشرح SQL Injection", "target": "SQL Injection",
                 "context_kind": "cybersecurity"},
                {"role": "assistant", "content": "توقفنا عند آلية الحدوث.", "context_kind": "cybersecurity"},
                {"role": "user", "content": "عدّل main.py", "context_kind": "work",
                 "conversation_domain": "work"},
            ],
            "exchange_archive": [
                {"user": "اشرح SQL Injection", "assistant": "توقفنا عند آلية الحدوث.",
                 "context_kind": "cybersecurity"},
                {"user": "عدّل main.py", "assistant": "تم التعديل",
                 "context_kind": "work", "conversation_domain": "work"},
            ],
        },
        version="test",
        project_root=str(project_root),
    )

    assert load_session()["session_id"] == work["session_id"]
    assert load_session()["session_type"] == "work"
    assert "dialogue_state" not in load_session()
    assert dialogue["session_type"] == "dialogue"
    assert "context_state" not in dialogue
    assert len(dialogue["dialogue_state"]["history"]) == 2
    assert len(dialogue["dialogue_state"]["exchange_archive"]) == 1
    latest_dialogue = get_latest_session_by_type("dialogue")
    assert latest_dialogue["dialogue_state"]["last_topic"] == "SQL Injection"


def test_restore_session_snapshot_obeys_session_type():
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.core.agent import Agent

    context = ContextStore()
    agent = Agent.__new__(Agent)
    agent.context = context
    agent.dialogue_memory = DialogueMemory(context)
    agent._pending_session = None

    assert agent.restore_session_snapshot({
        "session_type": "work",
        "dialogue_state": {"last_topic": "must not restore"},
        "context_state": {"current_file": "work.py"},
    }) is True
    assert agent.dialogue_memory.snapshot().get("last_topic") != "must not restore"
    assert context.current_file == "work.py"

    context.current_file = None
    assert agent.restore_session_snapshot({
        "session_type": "dialogue",
        "dialogue_state": {"last_topic": "SQL Injection", "history": []},
        "context_state": {"current_file": "stale-work.py"},
    }) is True
    assert agent.dialogue_memory.snapshot()["last_topic"] == "SQL Injection"
    assert context.current_file is None
