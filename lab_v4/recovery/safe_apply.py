# CyberLab Agent v4.0
# recovery/safe_apply.py

import os
from lab_v4.recovery.permissions import check_write
from lab_v4.recovery.snapshot import take
from lab_v4.recovery.rollback import rollback

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
