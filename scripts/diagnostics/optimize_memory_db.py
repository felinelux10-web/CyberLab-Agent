#!/usr/bin/env python3
"""Run bounded, non-destructive SQLite optimization after explicit confirmation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from lab_v4_dev.memory.db import DB_PATH, Database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that SQLite maintenance pragmas will run",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("pass --confirm to run non-destructive SQLite optimization")

    database = Database()
    try:
        database.connect()
        connection = database.conn
        optimize_result = connection.execute("PRAGMA optimize").fetchall()
        checkpoint = connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        connection.commit()
        report = {
            "database_path": str(DB_PATH),
            "status": "ok" if integrity == "ok" else "needs_review",
            "integrity_check": integrity,
            "optimize_result": [list(row) for row in optimize_result],
            "wal_checkpoint": list(checkpoint) if checkpoint is not None else None,
            "source_messages_deleted": False,
            "vacuum_run": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if integrity == "ok" else 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
