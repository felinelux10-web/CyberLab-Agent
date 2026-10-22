# CyberLab Agent v4.0
# recovery/rollback.py

import os
import shutil
from typing import Optional
from lab_v4_dev.recovery.snapshot import list_snapshots, SNAPSHOTS_DIR, _snapshot_key
from lab_v4_dev.core.audit import emit_event
from lab_v4_dev.recovery.permissions import check_write
from lab_v4_dev.recovery.path_policy import canonical_path, is_within


def _snapshot_matches_target(file_path: str, snapshot_path: str) -> bool:
    """Accept only archive snapshots whose filename identifies this target."""
    archive_root = canonical_path(SNAPSHOTS_DIR)
    candidate = canonical_path(snapshot_path)
    if not is_within(candidate, archive_root) or candidate == archive_root:
        return False
    name = os.path.basename(candidate)
    key = _snapshot_key(file_path)
    return (
        name.startswith((f"file__{key}__", f"new__{key}__"))
        and name.endswith(".snap")
    )


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

    # Keep trusted for API compatibility, but never let it bypass authorization.
    file_path = canonical_path(file_path)
    emit_event(
        "rollback.start",
        source="rollback",
        context={"file": file_path, "snapshot": snapshot_path},
        details={"trusted_provided": trusted, "effective_trusted": False},
    )

    # إذا لم يُحدد snapshot — خذ الأحدث
    if not snapshot_path:
        snaps = list_snapshots(file_path)
        if not snaps:
            emit_event("rollback.failed", source="rollback", context={"file": file_path}, details={"reason": "no_snapshots_found"})
            return {"status": "failed", "reason": "no_snapshots_found"}
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snaps[-1])

    snapshot_path = canonical_path(snapshot_path)
    if not os.path.exists(snapshot_path):
        emit_event("rollback.failed", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={"reason": "snapshot_not_found"})
        return {"status": "failed", "reason": "snapshot_not_found"}

    if not _snapshot_matches_target(file_path, snapshot_path):
        emit_event("rollback.rejected", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={"reason": "snapshot_target_mismatch"})
        return {"status": "failed", "reason": "snapshot_target_mismatch"}

    try:
        check_write(file_path)
    except Exception as e:
        emit_event("rollback.rejected", source="rollback", context={"file": file_path, "snapshot": snapshot_path}, details={"reason": str(e)})
        return {"status": "failed", "reason": str(e)}

    try:
        # A "new" snapshot means the target did not exist before the
        # transaction. Restoring it must restore absence, not create an empty file.
        if os.path.basename(snapshot_path).startswith(f"new__{_snapshot_key(file_path)}__"):
            if os.path.exists(file_path):
                os.remove(file_path)
        else:
            os.makedirs(os.path.dirname(file_path) or os.curdir, exist_ok=True)
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
