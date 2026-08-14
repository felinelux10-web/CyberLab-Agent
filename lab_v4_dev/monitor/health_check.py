# CyberLab Agent v4.0
# monitor/health_check.py

import os
import sqlite3
from lab_v4_dev.executor.throttle import get_ram_mb
from lab_v4_dev.core.config import HARD_LIMITS, FROZEN_ZONES

def check_health(state) -> dict:
    results = {}

    # RAM
    ram = get_ram_mb()
    results["ram_ok"] = ram < HARD_LIMITS["max_ram_mb"]
    results["ram_mb"] = round(ram, 2)

    # DB
    try:
        db_path = "lab_v4_dev/memory/agent.db"
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA integrity_check")
        conn.close()
        results["db_ok"] = True
    except Exception:
        results["db_ok"] = False

    # stable محمية
    try:
        test = "stable/v3.5/agent_memory.py"
        results["stable_ok"] = os.path.exists(test)
    except Exception:
        results["stable_ok"] = False

    # logs
    log_path = "lab_v4_dev/logs/agent.log"
    if os.path.exists(log_path):
        size_mb = os.path.getsize(log_path) / 1024 / 1024
        results["log_ok"] = size_mb < HARD_LIMITS["log_max_size_mb"]
        results["log_mb"] = round(size_mb, 3)
    else:
        results["log_ok"] = True
        results["log_mb"] = 0

    # state
    results["state_mode"] = state.mode
    results["state_ok"] = state.mode != "frozen"

    # النتيجة الكلية
    results["healthy"] = all([
        results["ram_ok"],
        results["db_ok"],
        results["stable_ok"],
        results["log_ok"],
        results["state_ok"],
    ])

    return results
