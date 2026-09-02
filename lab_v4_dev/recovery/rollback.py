# CyberLab Agent v4.0
# recovery/rollback.py

import os
import shutil
from typing import Optional
from lab_v4_dev.recovery.snapshot import list_snapshots, SNAPSHOTS_DIR
from lab_v4_dev.core.audit import emit_event
from lab_v4_dev.recovery.permissions import check_write


def rollback(file_path: str, snapshot_path: Optional[str] = None, trusted: bool = True) -> dict:
    """
    Restore a file from a snapshot.

    Security boundary:
    - By default (trusted=True) rollback is treated as an internal trusted primitive and
      will not perform a check_write(). This preserves existing internal recovery semantics.
    - If called with trusted=False, a check_write() is performed before attempting to restore
      to prevent accidental security bypass from untrusted callers.
    """

    emit_event("rollback.start", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={"trusted": trusted})

    # إذا لم يُحدد snapshot — خذ الأحدث
    if not snapshot_path:
        snaps = list_snapshots(file_path)
        if not snaps:
            emit_event("rollback.failed", source="rollback", context={"file": file_path}, details={"reason": "no_snapshots_found"})
            return {"status": "failed", "reason": "no_snapshots_found"}
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snaps[-1])

    if not os.path.exists(snapshot_path):
        emit_event("rollback.failed", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={"reason": "snapshot_not_found"})
        return {"status": "failed", "reason": "snapshot_not_found"}

    # Enforce write-check when the caller is untrusted
    if not trusted:
        try:
            check_write(file_path)
        except Exception as e:
            emit_event("rollback.rejected", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={"reason": str(e)})
            return {"status": "failed", "reason": str(e)}

    try:
        shutil.copy2(snapshot_path, file_path)
        emit_event("rollback.success", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={})
        return {
            "status": "ok",
            "restored": file_path,
            "from": snapshot_path,
        }
    except Exception as e:
        emit_event("rollback.failed", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={"reason": str(e)})
        return {"status": "failed", "reason": str(e)}
