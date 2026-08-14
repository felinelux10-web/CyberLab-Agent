"""
v5.6 — Security Guard
يفحص الأوامر والمسارات قبل التنفيذ
"""
import os
import re
from datetime import datetime

CYBERLAB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SECURITY_LOG  = os.path.join(CYBERLAB_ROOT, "workspace", "security_log.jsonl")

DANGEROUS_PATTERNS = [
    r"rm\s+-rf",
    r"chmod\s+777",
    r"chmod\s+\+s",
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/sd",
    r"fork\s*bomb",
    r":\(\)\{.*\}",
    r"base64\s+-d.*\|.*sh",
    r"curl.*\|\s*bash",
    r"wget.*\|\s*sh",
]

FORBIDDEN_PATHS = [
    "/etc", "/system", "/proc", "/dev",
    "/sys", "/root", "/data/system",
    "/data/data/com.termux/files/usr/etc",
]

def check_command(cmd: str) -> dict:
    """يفحص أمر bash قبل تنفيذه"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            _log_threat("dangerous_command", cmd, pattern)
            return {
                "safe": False,
                "reason": f"أمر خطير: يطابق النمط [{pattern}]",
                "cmd": cmd,
            }
    return {"safe": True, "cmd": cmd}

def check_path(path: str) -> dict:
    """يفحص مسار قبل القراءة أو الكتابة"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    for forbidden in FORBIDDEN_PATHS:
        if abs_path.startswith(forbidden):
            _log_threat("forbidden_path", path, forbidden)
            return {
                "safe": False,
                "reason": f"مسار محظور: {abs_path}",
                "path": abs_path,
            }
    return {"safe": True, "path": abs_path}

def _log_threat(threat_type: str, value: str, matched: str):
    """يحفظ التهديد في السجل الأمني"""
    import json
    os.makedirs(os.path.dirname(SECURITY_LOG), exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": threat_type,
        "value": value,
        "matched": matched,
    }
    with open(SECURITY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def get_security_log(limit: int = 20) -> list:
    """يعرض آخر التهديدات المسجلة"""
    import json
    if not os.path.exists(SECURITY_LOG):
        return []
    with open(SECURITY_LOG, encoding="utf-8") as f:
        lines = f.readlines()
    entries = []
    for line in reversed(lines[-limit:]):
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries
