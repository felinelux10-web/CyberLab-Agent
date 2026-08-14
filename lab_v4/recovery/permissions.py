# CyberLab Agent v4.0
# recovery/permissions.py

from lab_v4.core.config import FROZEN_ZONES

class FrozenZoneError(Exception):
    pass

def is_frozen(path: str) -> bool:
    for zone in FROZEN_ZONES:
        if path.startswith(zone):
            return True
    return False

def check_write(path: str):
    if is_frozen(path):
        raise FrozenZoneError(f"FROZEN ZONE — كتابة مرفوضة: {path}")

def check_delete(path: str):
    if is_frozen(path):
        raise FrozenZoneError(f"FROZEN ZONE — حذف مرفوض: {path}")
