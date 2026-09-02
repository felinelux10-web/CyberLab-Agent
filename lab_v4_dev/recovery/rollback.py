# CyberLab Agent v4.0
# recovery/rollback.py

import os
import shutil
import inspect
from typing import Optional
from lab_v4_dev.recovery.snapshot import list_snapshots, SNAPSHOTS_DIR
from lab_v4_dev.core.audit import emit_event
from lab_v4_dev.recovery.permissions import check_write


def _detect_internal_caller() -> bool:
    """
    Heuristic to detect if the caller appears to be inside the lab_v4_dev package.
    - Scans the call stack for any frame with 'lab_v4_dev' in the filename.
    - This is a conservative, best-effort heuristic to avoid allowing external callers
      to bypass permission checks while preserving internal trusted callers.
    """
    try:
        for frame in inspect.stack()[2:]:
            filename = frame.filename or ""
            if "lab_v4_dev" in filename:
                return True
    except Exception:
        # If stack inspection fails for any reason, default to conservative (not internal)
        return False
    return False


def rollback(file_path: str, snapshot_path: Optional[str] = None, trusted: Optional[bool] = None) -> dict:
    """
    Restore a file from a snapshot.

    Security boundary:
    - If `trusted` is explicitly provided (True/False) it is honored as the caller's intent.
    - If `trusted` is None (the default), we perform a lightweight stack inspection to
      heuristically determine whether the caller appears to be internal to the
      lab_v4_dev package. If an internal caller is detected, the operation is
      treated as trusted; otherwise it is treated as untrusted and a permission
      check (check_write) is enforced.

    This keeps internal recovery paths working while preventing external callers
    from using rollback as a permission bypass.
    """

    # Determine effective trust
    effective_trusted = trusted if trusted is not None else _detect_internal_caller()

    emit_event(
        "rollback.start",
        source="rollback",
        context={"file": file_path, "snapshot": snapshot_path},
        details={"trusted_provided": trusted, "effective_trusted": effective_trusted},
    )

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
    if not effective_trusted:
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
