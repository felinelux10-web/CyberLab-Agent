import json

import lab_v4_dev.core.repair.diff_approval as diff_approval


def _fake_safe_write(calls):
    def write(path, content, reason=""):
        calls.append((path, content, reason))
        target = diff_approval.os.path.abspath(path)
        diff_approval.os.makedirs(diff_approval.os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)
        return {"status": "success", "path": target}

    return write


def _pending(tmp_path, monkeypatch, calls, target, original="old", suggested="new"):
    monkeypatch.setattr(diff_approval, "PENDING_DIR", str(tmp_path / "pending"))
    monkeypatch.setattr(
        "lab_v4_dev.core.safe_io.safe_write",
        _fake_safe_write(calls),
    )
    return diff_approval.save_pending_fix(
        str(target),
        {
            "fix_type": "replace_line",
            "original": original,
            "suggested": suggested,
            "description": "stage6 test repair",
        },
        {"message": "test error"},
        {},
    )


def test_save_pending_fix_uses_safe_write(monkeypatch, tmp_path):
    calls = []
    path = _pending(tmp_path, monkeypatch, calls, tmp_path / "target.py")

    assert path.endswith(".json")
    assert calls
    assert calls[0][2] == "repair:create_pending_fix"
    assert json.loads((tmp_path / "pending" / path.split("/")[-1]).read_text())[
        "approved"
    ] is False


def test_apply_fix_requires_explicit_approval_and_does_not_write(monkeypatch, tmp_path):
    calls = []
    target = tmp_path / "target.py"
    target.write_text("old", encoding="utf-8")
    pending_path = _pending(tmp_path, monkeypatch, calls, target)
    calls.clear()

    result = diff_approval.apply_fix(pending_path)

    assert result["status"] == "needs_approval"
    assert target.read_text(encoding="utf-8") == "old"
    assert calls == []


def test_approved_apply_uses_safe_write_and_updates_pending(monkeypatch, tmp_path):
    calls = []
    target = tmp_path / "target.py"
    target.write_text("old", encoding="utf-8")
    pending_path = _pending(tmp_path, monkeypatch, calls, target)
    calls.clear()

    result = diff_approval.apply_fix(pending_path, approved=True)

    assert result["status"] == "success"
    assert target.read_text(encoding="utf-8") == "new"
    assert any(call[0] == str(target) for call in calls)
    pending = json.loads((tmp_path / "pending" / pending_path.split("/")[-1]).read_text())
    assert pending["approved"] is True
    assert pending["applied"] is True
