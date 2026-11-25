#!/usr/bin/env python3
"""Read-only SQLite integrity and provenance audit for the local memory store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from lab_v4_dev.memory.db import DB_PATH


def main() -> int:
    path = Path(DB_PATH)
    if not path.is_file():
        print(json.dumps({
            "status": "database_not_found",
            "database_path": str(path),
            "read_only": True,
        }, ensure_ascii=False, indent=2))
        return 2

    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        report = {
            "database_path": str(path),
            "database_size_bytes": path.stat().st_size,
            "read_only": True,
            "integrity_check": integrity,
            "tables": {},
            "checks": {},
        }
        for table in (
            "conversation_sessions",
            "conversation_messages",
            "memory_facts",
            "conversation_messages_fts",
            "conversation_messages_normalized_fts",
        ):
            if table in tables:
                report["tables"][table] = int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )

        if "conversation_messages" in tables:
            report["checks"]["duplicate_session_exchange_speaker_rows"] = int(
                connection.execute(
                    """SELECT COUNT(*) FROM (
                           SELECT session_id,exchange_id,speaker
                           FROM conversation_messages
                           GROUP BY session_id,exchange_id,speaker
                           HAVING COUNT(*)>1
                       )"""
                ).fetchone()[0]
            )

        if "memory_facts" in tables:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(memory_facts)")
            }
            required = {
                "valid_from", "invalidated_at", "supersedes",
                "verification", "origin",
            }
            report["checks"]["temporal_columns_present"] = sorted(required) <= columns
            if required <= columns:
                report["checks"]["active_facts_with_invalidation_time"] = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM memory_facts WHERE status='active' AND invalidated_at IS NOT NULL"
                    ).fetchone()[0]
                )
                report["checks"]["superseded_facts_without_invalidation_time"] = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM memory_facts WHERE status='superseded' AND invalidated_at IS NULL"
                    ).fetchone()[0]
                )
                if "conversation_messages" in tables:
                    report["checks"]["facts_with_missing_linked_source"] = int(
                        connection.execute(
                            """SELECT COUNT(*) FROM memory_facts f
                               LEFT JOIN conversation_messages m ON m.id=f.evidence_message_id
                               WHERE f.evidence_message_id IS NOT NULL AND m.id IS NULL"""
                        ).fetchone()[0]
                    )

        if "memory_migrations" in tables:
            report["checks"]["normalized_fts_rebuild_complete"] = (
                connection.execute(
                    "SELECT 1 FROM memory_migrations WHERE migration_key=?",
                    ("normalized_conversation_fts_v1",),
                ).fetchone() is not None
            )
            if (
                report["checks"]["normalized_fts_rebuild_complete"]
                and "conversation_messages_normalized_fts" in tables
                and "conversation_messages" in tables
            ):
                report["checks"]["normalized_fts_row_count_matches_messages"] = (
                    report["tables"]["conversation_messages_normalized_fts"]
                    == report["tables"]["conversation_messages"]
                )

        warnings = []
        if integrity != "ok":
            warnings.append("sqlite_integrity_check_failed")
        for key, value in report["checks"].items():
            if isinstance(value, int) and value > 0 and (
                "duplicate" in key or "missing" in key or "without_" in key or "with_invalidation" in key
            ):
                warnings.append(key)
            if key == "temporal_columns_present" and value is False:
                warnings.append(key)
            if key == "normalized_fts_row_count_matches_messages" and value is False:
                warnings.append(key)
        report["warnings"] = warnings
        report["status"] = "ok" if not warnings else "needs_review"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not warnings else 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
