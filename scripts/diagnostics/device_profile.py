#!/usr/bin/env python3
"""Read-only Android/Termux device and SQLite capability profile."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def _getprop(name: str) -> str | None:
    try:
        result = subprocess.run(
            ["getprop", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        value = result.stdout.strip()
        return value or None
    except (OSError, subprocess.SubprocessError):
        return None


def _meminfo_kib() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, remainder = line.partition(":")
                if key in {"MemTotal", "MemAvailable", "MemFree", "SwapTotal", "SwapFree"}:
                    token = remainder.strip().split()[0]
                    values[key] = int(token)
    except (OSError, ValueError, IndexError):
        pass
    return values


def _sqlite_fts5_available() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE fts5_probe USING fts5(content, tokenize='unicode61')"
        )
        connection.execute("DROP TABLE fts5_probe")
        return True
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def main() -> int:
    home = Path.home()
    storage = shutil.disk_usage(str(home))
    profile = {
        "device": {
            "manufacturer": _getprop("ro.product.manufacturer"),
            "model": _getprop("ro.product.model"),
            "device": _getprop("ro.product.device"),
            "android_release": _getprop("ro.build.version.release"),
            "sdk": _getprop("ro.build.version.sdk"),
            "abi": _getprop("ro.product.cpu.abi"),
        },
        "runtime": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "cpu_count": os.cpu_count(),
            "sqlite_version": sqlite3.sqlite_version,
            "sqlite_fts5_available": _sqlite_fts5_available(),
        },
        "memory_kib": _meminfo_kib(),
        "storage_bytes": {
            "path": str(home),
            "total": storage.total,
            "used": storage.used,
            "free": storage.free,
        },
        "safety": {
            "read_only": True,
            "database_modified": False,
            "repository_files_modified": False,
        },
    }
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
