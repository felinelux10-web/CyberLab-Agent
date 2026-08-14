# CyberLab Agent v4.0
# recovery/permissions.py
# DNI-9: أضيف فحص FORBIDDEN_PREFIXES (نظامي) بجانب FROZEN_ZONES (مشروع) — S1

import os
from lab_v4_dev.core.config import FROZEN_ZONES
from lab_v4_dev.core.project_context import FORBIDDEN_PREFIXES

class FrozenZoneError(Exception):
    pass

class SystemPathError(Exception):
    pass

def is_frozen(path: str) -> bool:
    for zone in FROZEN_ZONES:
        if path.startswith(zone):
            return True
    return False

def is_forbidden_system_path(path: str) -> bool:
    """يتحقق أن المسار ليس مساراً نظامياً حساساً (خارج أي مشروع)"""
    abs_path = os.path.abspath(path)
    return any(abs_path.startswith(p) for p in FORBIDDEN_PREFIXES)

def check_write(path: str):
    if is_forbidden_system_path(path):
        raise SystemPathError(f"SYSTEM PATH — كتابة مرفوضة: {path}")
    if is_frozen(path):
        raise FrozenZoneError(f"FROZEN ZONE — كتابة مرفوضة: {path}")

def check_delete(path: str):
    if is_forbidden_system_path(path):
        raise SystemPathError(f"SYSTEM PATH — حذف مرفوض: {path}")
    if is_frozen(path):
        raise FrozenZoneError(f"FROZEN ZONE — حذف مرفوض: {path}")
