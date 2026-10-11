# Project-scoped integration test for the canonical knowledge readers.
import json


def test_project_knowledge_readers_share_project_scoped_data(monkeypatch, tmp_path):
    import lab_v4_dev.core.project_context as context
    from lab_v4_dev.awareness import project_knowledge

    data_dir = tmp_path / "project_data"
    data_dir.mkdir()
    focus = "INTEGRATION_TEST_FOCUS"
    (data_dir / "roadmap.json").write_text(
        json.dumps({"current_focus": focus, "active": [], "planned": [], "completed": []}),
        encoding="utf-8",
    )
    (data_dir / "session_state.json").write_text(
        json.dumps({"active_goal": "SESSION_TEST_GOAL"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(context, "project_data_dir", lambda project_root=None: str(data_dir))
    project_knowledge.invalidate_cache()

    try:
        from lab_v4_dev.data.work_tracker import load_roadmap
        from lab_v4_dev.llm.prompt_builder import _load_roadmap
        from lab_v4_dev.memory.session_state import load_session

        assert project_knowledge.get_current_focus() == focus
        assert project_knowledge.get_roadmap()["current_focus"] == focus
        assert load_roadmap()["current_focus"] == focus
        assert _load_roadmap()["current_focus"] == focus
        assert project_knowledge.get_last_goal() == load_session()["active_goal"]
    finally:
        project_knowledge.invalidate_cache()
