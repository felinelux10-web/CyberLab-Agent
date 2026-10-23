import lab_v4_dev.core.sandbox_executor as sandbox_executor
import lab_v4_dev.core.security_guard as security_guard
import lab_v4_dev.executor.shell_runner as shell_runner


def test_shell_runner_calls_security_guard_before_subprocess(monkeypatch):
    seen = []

    def deny(command):
        seen.append(command)
        return {"safe": False, "reason": "DENIED_BY_STAGE1"}

    monkeypatch.setattr(security_guard, "check_command", deny)
    monkeypatch.setattr(shell_runner.subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("subprocess must not run after security rejection")
    ))

    result = shell_runner.run_shell("echo stage1")

    assert result["status"] == "blocked"
    assert result["stderr"] == "DNI-9 Security: DENIED_BY_STAGE1"
    assert seen == ["echo stage1"]


def test_sandbox_run_code_checks_path_and_command_before_subprocess(monkeypatch, tmp_path):
    checks = []
    script = tmp_path / "safe.py"
    script.write_text("print('safe')", encoding="utf-8")

    monkeypatch.setattr(security_guard, "check_path", lambda path: checks.append(("path", path)) or {"safe": True})
    monkeypatch.setattr(
        security_guard,
        "check_command",
        lambda command: checks.append(("command", command)) or {"safe": False, "reason": "DENIED_BY_STAGE1"},
    )
    monkeypatch.setattr(sandbox_executor.subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("subprocess must not run after security rejection")
    ))

    result = sandbox_executor.run_code(str(script))

    assert result["status"] == "blocked"
    assert result["error"] == "DENIED_BY_STAGE1"
    assert checks == [("path", str(script)), ("command", f"python3 {script}")]


def test_sandbox_run_code_rejects_path_before_checking_command(monkeypatch, tmp_path):
    script = tmp_path / "blocked.py"
    script.write_text("print('never')", encoding="utf-8")
    command_called = []

    monkeypatch.setattr(
        security_guard,
        "check_path",
        lambda _path: {"safe": False, "reason": "PATH_DENIED_BY_STAGE1"},
    )
    monkeypatch.setattr(
        security_guard,
        "check_command",
        lambda command: command_called.append(command) or {"safe": True},
    )

    result = sandbox_executor.run_code(str(script))

    assert result["status"] == "blocked"
    assert result["error"] == "PATH_DENIED_BY_STAGE1"
    assert command_called == []
