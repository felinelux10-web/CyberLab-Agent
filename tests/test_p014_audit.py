import json
from pathlib import Path

import lab_v4_dev.core.audit as audit


def test_audit_path_is_repository_rooted():
    repo_root = Path(__file__).resolve().parents[1]
    assert Path(audit.AUDIT_FILE) == repo_root / "execution_audit.json"


def test_emit_event_writes_to_configured_audit_path_not_cwd(tmp_path, monkeypatch):
    audit_path = tmp_path / "storage" / "execution_audit.json"
    audit_path.parent.mkdir(parents=True)
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()

    monkeypatch.setattr(audit, "AUDIT_FILE", str(audit_path))
    monkeypatch.chdir(unrelated_cwd)

    rec = audit.emit_event(
        "test.event", source="test", context={"a": 1}, details={"b": 2}
    )

    assert rec.event == "test.event"
    assert audit_path.exists()
    assert not (unrelated_cwd / "execution_audit.json").exists()

    data = json.loads(audit_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[-1]["event"] == "test.event"


def test_get_events_reads_newest_first_and_supports_evidence_filters(tmp_path, monkeypatch):
    audit_path = tmp_path / "execution_audit.json"
    monkeypatch.setattr(audit, "AUDIT_FILE", str(audit_path))
    audit.emit_event(
        "project.file_read", source="orchestrator",
        context={"project_root": "/projects/demo", "file_path": "/projects/demo/app.py"},
        details={"characters_read": 120},
    )
    audit.emit_event(
        "project.scan", source="orchestrator",
        context={"project_root": "/projects/demo"}, details={"total_files": 4},
    )
    audit.emit_event("unrelated.event", source="other", context={}, details={})
    events = audit.get_events(limit=10, source="orchestrator", event_prefix="project.")
    assert [item["event"] for item in events] == ["project.scan", "project.file_read"]
    assert events[0]["context"]["project_root"] == "/projects/demo"
    assert audit.get_events(limit=1, project_root="/projects/demo")[0]["event"] == "project.scan"


def test_project_knowledge_mutations_share_the_durable_audit_journal(tmp_path, monkeypatch):
    from lab_v4_dev.awareness import project_knowledge
    audit_path = tmp_path / "execution_audit.json"
    monkeypatch.setattr(audit, "AUDIT_FILE", str(audit_path))
    project_knowledge.clear_events()
    project_knowledge._emit("session_updated", {"goal": "knowledge context repair"})
    events = audit.get_events(limit=10, source="project_knowledge")
    assert events
    assert events[0]["event"] == "project_knowledge.session_updated"
    assert events[0]["details"]["goal"] == "knowledge context repair"
