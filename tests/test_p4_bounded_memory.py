from pathlib import Path


def _isolate(monkeypatch, tmp_path):
    import lab_v4_dev.core.project_context as context
    from lab_v4_dev.awareness import project_knowledge

    root = (tmp_path / "project").resolve()
    root.mkdir()
    monkeypatch.setattr(
        context,
        "project_index_dir",
        lambda project_root: str(tmp_path / "indices" / Path(project_root).name),
    )
    monkeypatch.setattr(context, "_active_project", context.ProjectContext(str(root)))
    project_knowledge.invalidate_cache()


def test_recent_session_archive_is_bounded_and_compact(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    from lab_v4_dev.memory import session_state

    for index in range(8):
        session_state._append_recent_archive({
            "session_id": f"session-{index}",
            "timestamp": f"2026-10-06T12:0{index}:00",
            "active_goal": f"goal-{index}",
            "completed_work": [f"done-{index}"],
            "next_step": f"step-{index}",
            "last_files": [f"file-{index}.py"],
            "dialogue_state": {"history": ["must not be archived"]},
            "context_state": {"subject": "topic"},
        })

    archive = session_state.get_recent_sessions()
    assert len(archive) == session_state.MAX_RECENT_SESSIONS == 5
    assert archive[0]["session_id"] == "session-3"
    assert archive[-1]["session_id"] == "session-7"
    assert all("dialogue_state" not in item for item in archive)
    assert all("context_state" not in item for item in archive)


def test_bounded_dialogue_and_compact_session_are_separate(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.memory.session_state import save_recoverable_checkpoint, load_session

    memory = DialogueMemory(ContextStore())
    for index in range(12):
        memory.state.add_turn(role="user", content=f"turn-{index}")
    snapshot = memory.snapshot()
    save_recoverable_checkpoint(
        active_goal="goal",
        next_step="next",
        dialogue_state=snapshot,
        context_state={"subject": "topic"},
    )
    saved = load_session()

    assert len(snapshot["history"]) == 8
    assert len(saved["dialogue_state"]["history"]) == 8
    assert saved["active_goal"] == "goal"
    assert saved["next_step"] == "next"
