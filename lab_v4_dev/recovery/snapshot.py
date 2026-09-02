# CyberLab Agent v4.0
# recovery/snapshot.py

import os
import hashlib
import shutil
from datetime import datetime
from typing import List
from lab_v4_dev.recovery.permissions import check_write
from lab_v4_dev.core.audit import emit_event

SNAPSHOTS_DIR = "lab_v4_dev/archives/snapshots"


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def take(file_path: str) -> dict:
    try:
        check_write(file_path)
    except Exception as e:
        emit_event("snapshot.rejected", source="snapshot", context={"file": file_path}, details={"reason": str(e)})
        raise

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = file_path.replace("/", "_").replace(".", "_")
    snapshot_name = f"{safe_name}__{timestamp}.snap"

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_name)

    # إذا الملف غير موجود — احفظ نسخة فارغة كمرجع
    if not os.path.exists(file_path):
        open(snapshot_path, "w").write("")
        rec = {
            "status": "ok",
            "original": file_path,
            "snapshot": snapshot_path,
            "hash": "",
            "timestamp": timestamp,
            "note": "new_file",
        }
        emit_event("snapshot.taken", source="snapshot", context={"file": file_path}, details={"snapshot": snapshot_path, "note": "new_file"})
        return rec

    shutil.copy2(file_path, snapshot_path)

    rec = {
        "status": "ok",
        "original": file_path,
        "snapshot": snapshot_path,
        "hash": _hash_file(file_path),
        "timestamp": timestamp,
    }

    emit_event("snapshot.taken", source="snapshot", context={"file": file_path}, details={"snapshot": snapshot_path})
    return rec


def list_snapshots(file_path: str) -> List[str]:
    if not os.path.exists(SNAPSHOTS_DIR):
        return []
    safe_name = file_path.replace("/", "_").replace(".", "_")
    snaps = [
        f for f in os.listdir(SNAPSHOTS_DIR)
        if f.startswith(safe_name)
    ]
    snaps = sorted(snaps)
    emit_event("snapshot.list", source="snapshot", context={"file": file_path}, details={"count": len(snaps)})
    return snaps
