# CyberLab Agent v4.0
# executor/throttle.py

import psutil
import os
from lab_v4_dev.core.config import HARD_LIMITS

def get_ram_mb() -> float:
    return psutil.Process().memory_info().rss / 1024 / 1024

def get_cpu_percent() -> float:
    # Android لا يسمح بـ /proc/stat
    # نستخدم cpu_percent للـ process الحالي فقط
    try:
        return psutil.Process().cpu_percent(interval=0.5)
    except Exception:
        return 0.0

def check_resources() -> dict:
    ram = get_ram_mb()
    cpu = get_cpu_percent()

    ram_ok = ram < HARD_LIMITS["max_ram_mb"]
    cpu_ok = cpu < HARD_LIMITS["max_cpu_percent"]

    return {
        "ram_mb" : round(ram, 2),
        "cpu_pct": round(cpu, 2),
        "ram_ok" : ram_ok,
        "cpu_ok" : cpu_ok,
        "ok"     : ram_ok and cpu_ok,
    }

def resources_ok() -> bool:
    return check_resources()["ok"]
