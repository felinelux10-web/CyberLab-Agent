# CyberLab Agent v4.0
# executor/shell_runner.py
# DNI-9 S4: أضيفت قائمة حظر لأوامر مدمّرة كطبقة دفاع مستقلة (defense in depth)

import subprocess
import re
from lab_v4_dev.core.config import HARD_LIMITS

DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/(?:\s|$)",
    r"rm\s+-rf\s+~(?:\s|$)",
    r"rm\s+-rf\s+\*",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
    r"\bmkfs\.",
    r"\bdd\s+if=",
    r">\s*/dev/sd[a-z]",
    r"\bchmod\s+-R\s+777\s+/(?:\s|$)",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
    r":/\s*$",
]

class DangerousCommandError(Exception):
    pass

def is_dangerous(command: str) -> bool:
    return any(re.search(p, command) for p in DANGEROUS_PATTERNS)

def run_shell(command: str, timeout: int = None) -> dict:
    if is_dangerous(command):
        return {
            "status": "blocked",
            "stdout": "",
            "stderr": f"DNI-9 Security: أمر مرفوض (نمط خطير مكتشف): {command}",
            "code"  : -1,
        }

    if timeout is None:
        timeout = HARD_LIMITS["task_timeout_sec"]

    try:
        result = subprocess.run(
            command,
            shell=True,
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
    except Exception as e:
        return {
            "status": "failed",
            "stdout": "",
            "stderr": str(e),
            "code"  : -1,
        }
