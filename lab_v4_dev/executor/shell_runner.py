# CyberLab Agent v4.0
# executor/shell_runner.py
# DNI-9 S4: أضيفت قائمة حظر لأوامر مدمّرة كطبقة دفاع مستقلة (defense in depth)

import subprocess
import shlex
from lab_v4_dev.core.config import HARD_LIMITS

class DangerousCommandError(Exception):
    pass


_SHELL_OPERATORS = {"|", "||", ";", "&&", ">", ">>", "<", "2>", "2>>"}


def _parse_command(command: str) -> list[str]:
    """Parse one executable command without invoking a shell."""
    if any(marker in command for marker in ("$((", "$(", "`")):
        raise ValueError("shell command substitution is not supported")
    argv = shlex.split(command, posix=True)
    if not argv:
        raise ValueError("empty command")
    if any(token in _SHELL_OPERATORS for token in argv):
        raise ValueError("shell operators are not supported; submit one command at a time")
    return argv

def is_dangerous(command: str) -> bool:
    from lab_v4_dev.core.security_guard import is_dangerous as guard_is_dangerous

    return guard_is_dangerous(command)

def run_shell(command: str, timeout: int = None) -> dict:
    from lab_v4_dev.core.security_guard import check_command

    security = check_command(command)
    if not security.get("safe", False):
        return {
            "status": "blocked",
            "stdout": "",
            "stderr": "DNI-9 Security: " + security.get(
                "reason", "الأمر مرفوض من حارس الأمان"
            ),
            "code": -1,
            "security": security,
        }

    if timeout is None:
        timeout = HARD_LIMITS["task_timeout_sec"]

    try:
        argv = _parse_command(command)
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            return {
                "status": "failed",
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "code"  : result.returncode,
            }

        return {
            "status": "ok",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "code"  : result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
            "code"  : -1,
        }
    except ValueError as e:
        return {
            "status": "blocked",
            "stdout": "",
            "stderr": f"DNI-9 Security: {e}",
            "code": -1,
        }
    except Exception as e:
        return {
            "status": "failed",
            "stdout": "",
            "stderr": str(e),
            "code"  : -1,
        }
