# CyberLab Agent v4.0
# recovery/safe_apply.py
# DNI-9 S2: أضيف فحص صياغة (ast.parse) لملفات .py قبل الاستبدال

import os
import ast
from typing import Optional
from lab_v4_dev.recovery.permissions import check_write
from lab_v4_dev.recovery.snapshot import take
from lab_v4_dev.recovery.rollback import rollback
from lab_v4_dev.core.audit import emit_event


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
        emit_event("safe_apply.rejected", source="safe_apply", context={"file": file_path}, details={"reason": str(e)})
        return {"status": "rejected", "reason": str(e)}

    emit_event("safe_apply.start", source="safe_apply", context={"file": file_path})

    # 2. خذ snapshot
    snap = take(file_path)
    emit_event("safe_apply.snapshot", source="safe_apply", context={"file": file_path}, details={"snapshot": snap.get("snapshot"), "status": snap.get("status")})
    if snap["status"] not in ["ok", "skipped"]:
        emit_event("safe_apply.snapshot_failed", source="safe_apply", context={"file": file_path}, details={"snapshot_status": snap.get("status")})
        return {"status": "failed", "reason": "snapshot_failed"}

    # 3. اكتب في ملف مؤقت أولاً
    tmp_path = file_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        emit_event("safe_apply.write_failed", source="safe_apply", context={"file": file_path}, details={"reason": str(e)})
        return {"status": "failed", "reason": f"write_failed: {e}"}

    # 4. تحقق من الملف المؤقت
    try:
        with open(tmp_path, "r", encoding="utf-8") as f:
            verified = f.read()
        if verified != new_content:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            emit_event("safe_apply.verify_failed", source="safe_apply", context={"file": file_path})
            return {"status": "failed", "reason": "verify_failed"}
    except Exception as e:
        emit_event("safe_apply.verify_error", source="safe_apply", context={"file": file_path}, details={"error": str(e)})
        return {"status": "failed", "reason": f"verify_error: {e}"}

    # 4.5 فحص الصياغة (DNI-9 S2)
    validation = _validate_syntax(file_path, new_content)
    if not validation["ok"]:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        emit_event("safe_apply.syntax_error", source="safe_apply", context={"file": file_path}, details={"error": validation.get("error")})
        return {"status": "failed", "reason": f"syntax_error: {validation['error']}"}

    # 5. استبدل الملف الأصلي
    try:
        os.replace(tmp_path, file_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        # Attempt rollback to previous snapshot
        try:
            rollback(file_path, snap.get("snapshot"))
        except Exception as e2:
            # Surface rollback failure for observability but do not break caller
            emit_event("safe_apply.rollback_failed", source="safe_apply", context={"file": file_path}, details={"error": str(e2)})
        emit_event("safe_apply.replace_failed", source="safe_apply", context={"file": file_path}, details={"reason": str(e)})
        return {"status": "failed", "reason": f"replace_failed: {e}"}

    emit_event("safe_apply.success", source="safe_apply", context={"file": file_path}, details={"snapshot": snap.get("snapshot")})
    return {
        "status": "ok",
        "file": file_path,
        "snapshot": snap.get("snapshot"),
    }
