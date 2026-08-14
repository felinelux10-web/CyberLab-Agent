# CyberLab Agent v4.0
# recovery/rollback.py

import os
import shutil
from lab_v4.recovery.snapshot import list_snapshots, SNAPSHOTS_DIR

def rollback(file_path: str, snapshot_path: str = None) -> dict:

    # إذا لم يُحدد snapshot — خذ الأحدث
    if not snapshot_path:
        snaps = list_snapshots(file_path)
        if not snaps:
            return {"status": "failed", "reason": "no_snapshots_found"}
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snaps[-1])

    if not os.path.exists(snapshot_path):
        return {"status": "failed", "reason": "snapshot_not_found"}

    try:
        shutil.copy2(snapshot_path, file_path)
        return {
            "status"  : "ok",
            "restored": file_path,
            "from"    : snapshot_path,
        }
    except Exception as e:
        return {"status": "failed", "reason": str(e)}
