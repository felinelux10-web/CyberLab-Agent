# CyberLab Agent v4.0
# recovery/snapshot.py

import os
import hashlib
import shutil
from datetime import datetime
from typing import List
from lab_v4_dev.recovery.permissions import check_write
from lab_v4_dev.recovery.path_policy import canonical_path
from lab_v4_dev.core.audit import emit_event
from lab_v4_dev.core.project_context import CYBERLAB_ROOT

SNAPSHOTS_DIR = os.path.join(CYBERLAB_ROOT, "lab_v4_dev", "archives", "snapshots")
_DEFAULT_SNAPSHOTS_DIR = os.path.realpath(SNAPSHOTS_DIR)
_TEST_RUNTIME_ENV = "CYBERLAB_TEST_RUNTIME_DIR"


def get_snapshots_dir(configured_dir: str = None) -> str:
    """Resolve the archive destination, isolating only the default path in pytest.

    A caller-supplied or monkeypatched directory is intentional and is never
    replaced by the test-runtime fallback.
    """
    configured = SNAPSHOTS_DIR if configured_dir is None else configured_dir
    runtime_dir = os.environ.get(_TEST_RUNTIME_ENV)
    if runtime_dir and os.path.realpath(configured) == _DEFAULT_SNAPSHOTS_DIR:
        return os.path.join(runtime_dir, "archives", "snapshots")
    return configured


def _snapshot_key(file_path: str) -> str:
    """Stable, collision-resistant identity for a canonical target path."""
    return hashlib.sha256(canonical_path(file_path).encode("utf-8")).hexdigest()


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def take(file_path: str) -> dict:
    file_path = canonical_path(file_path)
    try:
        check_write(file_path)
    except Exception as e:
        emit_event("snapshot.rejected", source="snapshot", context={"file": file_path}, details={"reason": str(e)})
        raise

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    existed_before = os.path.exists(file_path)
    kind = "file" if existed_before else "new"
    snapshot_name = f"{kind}__{_snapshot_key(file_path)}__{timestamp}.snap"

    snapshots_dir = get_snapshots_dir()
    os.makedirs(snapshots_dir, exist_ok=True)
    snapshot_path = os.path.join(snapshots_dir, snapshot_name)

    if not existed_before:
        with open(snapshot_path, "w", encoding="utf-8") as handle:
            handle.write("")
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
    file_path = canonical_path(file_path)
    snapshots_dir = get_snapshots_dir()
    if not os.path.exists(snapshots_dir):
        return []
    key = _snapshot_key(file_path)
    prefixes = (f"file__{key}__", f"new__{key}__")
    snaps = [
        f for f in os.listdir(snapshots_dir)
        if f.startswith(prefixes) and f.endswith(".snap")
    ]
    snaps = sorted(snaps)
    emit_event("snapshot.list", source="snapshot", context={"file": file_path}, details={"count": len(snaps)})
    return snaps
