# CyberLab Agent v4.0
# monitor/health_check.py

import os
import sqlite3
from pathlib import Path
from lab_v4_dev.executor.throttle import get_ram_mb
from lab_v4_dev.core.config import HARD_LIMITS, FROZEN_ZONES

ROOT_DIR = Path(__file__).resolve().parents[2]

def check_health(state) -> dict:
    results = {}

    # RAM
    ram = get_ram_mb()
    results["ram_ok"] = ram < HARD_LIMITS["max_ram_mb"]
    results["ram_mb"] = round(ram, 2)

    # DB
    try:
        db_path = ROOT_DIR / "lab_v4_dev" / "memory" / "agent.db"
        with sqlite3.connect(str(db_path), timeout=3) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
        results["db_ok"] = bool(integrity and integrity[0] == "ok")
    except (OSError, sqlite3.Error):
        results["db_ok"] = False

    # The active runtime is lab_v4_dev. A legacy stable tree is optional;
    # if it exists, preserve the original integrity requirement for its protected
    # v3.5 memory file. Its absence must not make the canonical runtime unhealthy.
    try:
        stable_root = ROOT_DIR / "stable"
        if not stable_root.exists():
            results["stable_ok"] = True
            results["stable_status"] = "not_installed"
        else:
            test = stable_root / "v3.5" / "agent_memory.py"
            results["stable_ok"] = test.is_file()
            results["stable_status"] = (
                "verified" if results["stable_ok"] else "required_file_missing"
            )
    except OSError:
        results["stable_ok"] = False
        results["stable_status"] = "check_error"

    # logs
    log_path = ROOT_DIR / "lab_v4_dev" / "logs" / "agent.log"
    if log_path.exists():
        size_mb = log_path.stat().st_size / 1024 / 1024
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
