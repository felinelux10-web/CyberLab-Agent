from pathlib import Path


def test_project_data_paths_are_distinct_and_canonical(tmp_path, monkeypatch):
    import lab_v4_dev.core.project_context as context

    base = Path(context.BASE_PROJECT_ROOT).resolve()
    project_a = (tmp_path / "project_a").resolve()
    project_b = (tmp_path / "project_b").resolve()
    project_a.mkdir()
    project_b.mkdir()

    monkeypatch.setattr(
        context,
        "project_index_dir",
        lambda root: str(tmp_path / "indices" / Path(root).name),
    )

    assert context.project_data_dir(str(base)) == str(base / "project_data")
    assert context.project_data_file("session_state.json", str(project_a)) != context.project_data_file(
        "session_state.json", str(project_b)
    )
    assert context.project_data_file("session_state.json", str(project_a)).startswith(
        str(tmp_path / "indices" / "project_a")
    )


def test_project_knowledge_state_does_not_leak_between_active_projects(tmp_path, monkeypatch):
    import lab_v4_dev.core.project_context as context
    from lab_v4_dev.awareness import project_knowledge

    project_a = (tmp_path / "project_a").resolve()
    project_b = (tmp_path / "project_b").resolve()
    project_a.mkdir()
    project_b.mkdir()
    monkeypatch.setattr(
        context,
        "project_index_dir",
        lambda root: str(tmp_path / "indices" / Path(root).name),
    )
    monkeypatch.setattr(context, "_active_project", context.ProjectContext(str(project_a)))
    project_knowledge.invalidate_cache()
    project_knowledge.save_roadmap({"marker": "A"})

    monkeypatch.setattr(context, "_active_project", context.ProjectContext(str(project_b)))
    project_knowledge.invalidate_cache()
    assert project_knowledge.get_roadmap() == {}
    project_knowledge.save_roadmap({"marker": "B"})

    monkeypatch.setattr(context, "_active_project", context.ProjectContext(str(project_a)))
    project_knowledge.invalidate_cache()
    assert project_knowledge.get_roadmap() == {"marker": "A"}


def test_switching_projects_does_not_delete_existing_index(monkeypatch, tmp_path):
    import lab_v4_dev.core.project_context as context

    project_a = (tmp_path / "project_a").resolve()
    project_b = (tmp_path / "project_b").resolve()
    project_a.mkdir()
    project_b.mkdir()
    index_a = tmp_path / "index_a"
    index_b = tmp_path / "index_b"
    index_a.mkdir()
    index_b.mkdir()
    (index_a / "project_snapshot.json").write_text("{}", encoding="utf-8")
    (index_b / "project_snapshot.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        context,
        "project_index_dir",
        lambda root: str(index_a if Path(root).name == "project_a" else index_b),
    )
    monkeypatch.setattr(context, "_active_project", context.ProjectContext(str(project_a)))
    monkeypatch.setattr(context, "load_registry", lambda: {})
    monkeypatch.setattr(context, "save_registry", lambda _data: None)
    monkeypatch.setattr(context, "register_project", lambda _project: None)

    result = context.set_active_project(str(project_b))
    assert result["status"] == "success"
    assert (index_a / "project_snapshot.json").exists()
    assert (index_b / "project_snapshot.json").exists()
