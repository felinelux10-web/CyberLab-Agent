import json
import os
from lab_v4_dev.core.audit import emit_event


def test_emit_event_writes_audit(tmp_path, monkeypatch):
    # Use tmp_path as cwd so audit file is created there
    monkeypatch.chdir(tmp_path)
    # Ensure no pre-existing file
    audit_path = tmp_path / "execution_audit.json"
    if audit_path.exists():
        audit_path.unlink()

    rec = emit_event("test.event", source="test", context={"a": 1}, details={"b": 2})
    assert rec.event == "test.event"
    assert os.path.exists(str(audit_path))

    data = json.loads(audit_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[-1]["event"] == "test.event"
