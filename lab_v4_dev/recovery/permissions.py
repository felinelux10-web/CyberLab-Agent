# CyberLab Agent v4.0
# recovery/permissions.py
# DNI-9: أضيف فحص FORBIDDEN_PREFIXES (نظامي) بجانب FROZEN_ZONES (مشروع) — S1

from lab_v4_dev.recovery.path_policy import canonical_path, is_forbidden_system_path, is_frozen

class FrozenZoneError(Exception):
    pass

class SystemPathError(Exception):
    pass

def check_write(path: str):
    path = canonical_path(path)
    if is_forbidden_system_path(path):
        raise SystemPathError(f"SYSTEM PATH — كتابة مرفوضة: {path}")
    if is_frozen(path):
        raise FrozenZoneError(f"FROZEN ZONE — كتابة مرفوضة: {path}")

def check_delete(path: str):
    path = canonical_path(path)
    if is_forbidden_system_path(path):
        raise SystemPathError(f"SYSTEM PATH — حذف مرفوض: {path}")
    if is_frozen(path):
        raise FrozenZoneError(f"FROZEN ZONE — حذف مرفوض: {path}")
