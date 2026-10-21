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
