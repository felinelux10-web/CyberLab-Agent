# CyberLab Agent v4.0
# recovery/safe_apply.py
# DNI-9 S2: أضيف فحص صياغة (ast.parse) لملفات .py قبل الاستبدال

import os
import ast
from lab_v4_dev.recovery.permissions import check_write
from lab_v4_dev.recovery.snapshot import take
from lab_v4_dev.recovery.rollback import rollback

def _validate_syntax(file_path: str, content: str) -> dict:
    if not file_path.endswith(".py"):
        return {"ok": True}
    try:
        ast.parse(content)
        return {"ok": True}
    except SyntaxError as e:
        return {"ok": False, "error": str(e)}
    except Exception:
        return {"ok": True}

def safe_apply(file_path: str, new_content: str) -> dict:

    # 1. تحقق من الصلاحيات
    try:
        check_write(file_path)
    except Exception as e:
        return {"status": "rejected", "reason": str(e)}

    # 2. خذ snapshot
    snap = take(file_path)
    if snap["status"] not in ["ok", "skipped"]:
        return {"status": "failed", "reason": "snapshot_failed"}

    # 3. اكتب في ملف مؤقت أولاً
    tmp_path = file_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return {"status": "failed", "reason": f"write_failed: {e}"}

    # 4. تحقق من الملف المؤقت
    try:
        with open(tmp_path, "r", encoding="utf-8") as f:
            verified = f.read()
        if verified != new_content:
            os.remove(tmp_path)
            return {"status": "failed", "reason": "verify_failed"}
    except Exception as e:
        return {"status": "failed", "reason": f"verify_error: {e}"}

    # 4.5 فحص الصياغة (DNI-9 S2)
    validation = _validate_syntax(file_path, new_content)
    if not validation["ok"]:
        os.remove(tmp_path)
        return {"status": "failed", "reason": f"syntax_error: {validation['error']}"}

    # 5. استبدل الملف الأصلي
    try:
        os.replace(tmp_path, file_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        rollback(file_path, snap.get("snapshot"))
        return {"status": "failed", "reason": f"replace_failed: {e}"}

    return {
        "status"  : "ok",
        "file"    : file_path,
        "snapshot": snap.get("snapshot"),
    }
