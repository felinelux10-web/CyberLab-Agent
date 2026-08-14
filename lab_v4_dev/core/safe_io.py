"""
v5.3 — Safety & Transaction Foundation
دالة موحّدة لكتابة الملفات: Backup + Audit Log + Whitelist
DNI-9 S3: أضيف فحص صياغة (ast.parse) + ربط بنظام Snapshot الموحّد
"""
import os
import json
import shutil
import ast
from datetime import datetime
from lab_v4_dev.recovery.snapshot import take as snapshot_take

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AUDIT_LOG_PATH = os.path.join(PROJECT_ROOT, "workspace", "audit_log.jsonl")

# المسارات المسموح للوكيل بالكتابة فيها (نسبية لـ PROJECT_ROOT)
ALLOWED_WRITE_PREFIXES = [
    "lab_v4_dev",
    "workspace",
]

def _is_allowed(path: str) -> bool:
    """يتحقق أن المسار داخل المسارات المسموحة فقط"""
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(PROJECT_ROOT):
        return False
    rel = os.path.relpath(abs_path, PROJECT_ROOT)
    return any(rel.startswith(prefix) for prefix in ALLOWED_WRITE_PREFIXES)

def _log_event(event: dict):
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    event["timestamp"] = datetime.now().isoformat()
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def _validate_syntax(path: str, content: str) -> dict:
    if not path.endswith(".py"):
        return {"ok": True}
    try:
        ast.parse(content)
        return {"ok": True}
    except SyntaxError as e:
        return {"ok": False, "error": str(e)}
    except Exception:
        return {"ok": True}

def safe_write(path: str, content: str, reason: str = "") -> dict:
    """
    كتابة آمنة لملف: تأخذ backup + snapshot موحّد قبل التعديل، تفحص الصياغة، وتسجل العملية.
    تُرفض إذا كان المسار خارج المسارات المسموحة أو الصياغة غير صحيحة.
    """
    if not _is_allowed(path):
        _log_event({"op": "write", "path": path, "status": "denied",
                     "reason": "path not in whitelist"})
        return {"status": "denied", "message": f"غير مسموح بالكتابة في: {path}"}

    validation = _validate_syntax(path, content)
    if not validation["ok"]:
        _log_event({"op": "write", "path": path, "status": "denied",
                     "reason": f"syntax_error: {validation['error']}"})
        return {"status": "denied", "message": f"خطأ صياغة: {validation['error']}"}

    backup_path = None
    snapshot_path = None
    if os.path.exists(path):
        backup_path = path + ".bak"
        shutil.copy2(path, backup_path)
        snap = snapshot_take(path)
        if snap.get("status") == "ok":
            snapshot_path = snap.get("snapshot")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    _log_event({
        "op": "write", "path": path, "status": "success",
        "backup": backup_path, "snapshot": snapshot_path, "reason": reason,
        "size_bytes": len(content.encode("utf-8")),
    })

    return {"status": "success", "path": path, "backup": backup_path, "snapshot": snapshot_path}


def safe_delete(path: str, reason: str = "") -> dict:
    """حذف آمن مع backup + snapshot + audit"""
    from lab_v4_dev.recovery.permissions import check_delete

    if not os.path.exists(path):
        return {"status": "failed", "message": "الملف غير موجود"}

    check_delete(path)

    backup_path = path + ".bak"
    shutil.copy2(path, backup_path)

    snap = snapshot_take(path)
    snapshot_path = snap.get("snapshot") if snap.get("status") == "ok" else None

    os.remove(path)

    _log_event({
        "op": "delete",
        "path": path,
        "status": "success",
        "backup": backup_path,
        "snapshot": snapshot_path,
        "reason": reason,
    })

    return {
        "status": "success",
        "path": path,
        "backup": backup_path,
        "snapshot": snapshot_path,
    }

def get_audit_log(limit: int = 10) -> list:
    """آخر العمليات المسجلة"""
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    events = [json.loads(l) for l in lines[-limit:]]
    return list(reversed(events))
