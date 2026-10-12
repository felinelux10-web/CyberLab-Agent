"""Canonical path policy shared by write and recovery layers."""
import os
from lab_v4_dev.core.config import FROZEN_ZONES
from lab_v4_dev.core.project_context import CYBERLAB_ROOT, FORBIDDEN_PREFIXES

def canonical_path(path):
    """Resolve absolute path and symlinked parents before authorization."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(os.fspath(path))))

def is_within(path, root):
    target, base = canonical_path(path), canonical_path(root)
    try:
        return os.path.commonpath((target, base)) == base
    except (ValueError, OSError):
        return False

def is_forbidden_system_path(path):
    target = canonical_path(path)
    return any(is_within(target, root) for root in FORBIDDEN_PREFIXES)

def is_frozen(path):
    target, root = canonical_path(path), canonical_path(CYBERLAB_ROOT)
    if not is_within(target, root):
        return False
    relative = os.path.relpath(target, root).replace(os.sep, "/").casefold()
    for zone in FROZEN_ZONES:
        frozen = str(zone).replace("\\", "/").strip("/").casefold()
        if frozen and (relative == frozen or relative.startswith(frozen + "/")):
            return True
    return False
