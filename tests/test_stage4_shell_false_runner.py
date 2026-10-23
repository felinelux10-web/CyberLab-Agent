import subprocess

import lab_v4_dev.executor.shell_runner as shell_runner
from lab_v4_dev.core.config import HARD_LIMITS


def test_run_shell_executes_argv_without_shell(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="hello\n", stderr="")

    monkeypatch.setattr(shell_runner.subprocess, "run", fake_run)

    result = shell_runner.run_shell("echo 'hello'")

    assert result["status"] == "ok"
    assert calls == [
        ((["echo", "hello"],), {
            "shell": False,
            "capture_output": True,
            "text": True,
            "timeout": HARD_LIMITS["task_timeout_sec"],
        })
    ]


def test_run_shell_rejects_shell_operators_without_invoking_subprocess(monkeypatch):
    monkeypatch.setattr(
        shell_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("shell operators must be rejected before subprocess")
        ),
    )

    result = shell_runner.run_shell("echo safe | cat")

    assert result["status"] == "blocked"
    assert "shell operators" in result["stderr"]


def test_run_shell_rejects_command_substitution(monkeypatch):
    monkeypatch.setattr(
        shell_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("command substitution must not execute")
        ),
    )

    result = shell_runner.run_shell("echo $(id)")

    assert result["status"] == "blocked"
    assert "command substitution" in result["stderr"]
