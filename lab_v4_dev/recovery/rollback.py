# CyberLab Agent v4.0
# recovery/rollback.py

import os
import shutil
from typing import Optional
from lab_v4_dev.recovery.snapshot import (
    list_snapshots,
    SNAPSHOTS_DIR,
    _snapshot_key,
    get_snapshots_dir,
)
from lab_v4_dev.core.audit import emit_event
from lab_v4_dev.recovery.permissions import check_write
from lab_v4_dev.recovery.path_policy import canonical_path, is_within


def _snapshot_matches_target(file_path: str, snapshot_path: str) -> bool:
    """Accept only archive snapshots whose filename identifies this target."""
    archive_root = canonical_path(get_snapshots_dir(SNAPSHOTS_DIR))
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
    - Explicit trusted values remain API-compatible but do not bypass authorization.
    - The write permission check is always enforced before restoring a target.
    """
    file_path = canonical_path(file_path)
    emit_event(
        "rollback.start",
        source="rollback",
        context={"file": file_path, "snapshot": snapshot_path},
        details={"trusted_provided": trusted, "effective_trusted": False},
    )

    snapshots_dir = get_snapshots_dir(SNAPSHOTS_DIR)
    if not snapshot_path:
        snaps = list_snapshots(file_path)
        if not snaps:
            emit_event("rollback.failed", source="rollback", context={"file": file_path}, details={"reason": "no_snapshots_found"})
            return {"status": "failed", "reason": "no_snapshots_found"}
        snapshot_path = os.path.join(snapshots_dir, snaps[-1])

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
