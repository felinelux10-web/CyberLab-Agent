# CyberLab Agent v4.0
# executor/shell_runner.py

import subprocess
from lab_v4.core.config import HARD_LIMITS

def run_shell(command: str, timeout: int = None) -> dict:
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
