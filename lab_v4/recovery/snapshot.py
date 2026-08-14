# CyberLab Agent v4.0
# recovery/snapshot.py

import os
import hashlib
import shutil
from datetime import datetime
from lab_v4.recovery.permissions import check_write

SNAPSHOTS_DIR = "lab_v4/archives/snapshots"

def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def take(file_path: str) -> dict:
    check_write(file_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = file_path.replace("/", "_").replace(".", "_")
    snapshot_name = f"{safe_name}__{timestamp}.snap"

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_name)

    # إذا الملف غير موجود — احفظ نسخة فارغة كمرجع
    if not os.path.exists(file_path):
        open(snapshot_path, "w").write("")
        return {
            "status"   : "ok",
            "original" : file_path,
            "snapshot" : snapshot_path,
            "hash"     : "",
            "timestamp": timestamp,
            "note"     : "new_file"
        }

    shutil.copy2(file_path, snapshot_path)

    return {
        "status"   : "ok",
        "original" : file_path,
        "snapshot" : snapshot_path,
        "hash"     : _hash_file(file_path),
        "timestamp": timestamp,
    }

def list_snapshots(file_path: str) -> list:
    if not os.path.exists(SNAPSHOTS_DIR):
        return []
    safe_name = file_path.replace("/", "_").replace(".", "_")
    snaps = [
        f for f in os.listdir(SNAPSHOTS_DIR)
        if f.startswith(safe_name)
    ]
    return sorted(snaps)
