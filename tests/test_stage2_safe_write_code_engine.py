import pytest

import lab_v4_dev.core.code_engine as code_engine


def test_save_file_delegates_to_safe_write(monkeypatch):
    calls = []

    def fake_safe_write(path, content, reason=""):
        calls.append((path, content, reason))
        return {"status": "success", "path": "/workspace/scripts/generated.py"}

    monkeypatch.setattr("lab_v4_dev.core.safe_io.safe_write", fake_safe_write)

    result = code_engine.save_file("print('ok')", "generated.py", "scripts")

    assert result == "workspace/scripts/generated.py"
    assert calls == [
        (
            "workspace/scripts/generated.py",
            "print('ok')",
            "code_engine.save_file:scripts/generated.py",
        )
    ]


def test_save_file_does_not_report_success_when_safe_write_denies(monkeypatch):
    calls = []

    def deny(path, content, reason=""):
        calls.append((path, content, reason))
        return {"status": "denied", "message": "WRITE_DENIED_BY_POLICY"}

    monkeypatch.setattr("lab_v4_dev.core.safe_io.safe_write", deny)

    with pytest.raises(PermissionError, match="WRITE_DENIED_BY_POLICY"):
        code_engine.save_file("print('blocked')", "blocked.py", "scripts")

    assert calls


def test_save_file_does_not_use_direct_open(monkeypatch):
    def fail_open(*_args, **_kwargs):
        raise AssertionError("code_engine.save_file must use safe_write")

    monkeypatch.setattr(code_engine, "open", fail_open, raising=False)
    monkeypatch.setattr(
        "lab_v4_dev.core.safe_io.safe_write",
        lambda path, content, reason="": {"status": "success", "path": path},
    )

    assert code_engine.save_file("print('safe')", "safe.py") == "workspace/scripts/safe.py"
