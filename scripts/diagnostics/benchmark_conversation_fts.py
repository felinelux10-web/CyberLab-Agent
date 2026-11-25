#!/usr/bin/env python3
"""Read-only FTS5/LIKE latency benchmark for the installed conversation archive."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from lab_v4_dev.memory.db import DB_PATH
from lab_v4_dev.memory.conversation_archive import ConversationArchive


QUERIES = (
    "سماكة الجبس",
    "الأدوات التي استخدمتها",
    "الألوان الذهبية والبيضاء والزرقاء",
    "الصباغة المائية",
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def _tokens(query: str) -> list[str]:
    stop = {
        "ما", "ماذا", "هل", "هي", "هو", "الذي", "التي", "من", "في",
        "عن", "على", "الى", "إلى", "مع", "هذا", "هذه", "ذلك",
        "the", "what", "which", "did", "do", "i", "you", "me", "my",
    }
    return [
        token for token in re.findall(r"[\w\u0600-\u06ff]+", query, flags=re.UNICODE)
        if token.casefold().replace("أ", "ا").replace("إ", "ا") not in stop
    ][:20]


def _run_query(connection, query: str, session_id: str | None, *, fts: bool) -> int:
    if fts:
        expression = ConversationArchive._fts_query(query)
        if not expression:
            return 0
        sql = (
            "SELECT m.id FROM conversation_messages_fts f "
            "JOIN conversation_messages m ON m.id=f.rowid "
            "WHERE conversation_messages_fts MATCH ?"
        )
        params: list[object] = [expression]
        if session_id:
            sql += " AND m.session_id=?"
            params.append(session_id)
        sql += " ORDER BY m.id DESC LIMIT 8"
        return len(connection.execute(sql, params).fetchall())

    tokens = _tokens(query) or [query]
    sql = (
        "SELECT id FROM conversation_messages WHERE ("
        + " OR ".join("content LIKE ?" for _ in tokens)
        + ")"
    )
    params = ["%" + token + "%" for token in tokens]
    if session_id:
        sql += " AND session_id=?"
        params.append(session_id)
    sql += " ORDER BY id DESC LIMIT 8"
    return len(connection.execute(sql, params).fetchall())


def _run_normalized_query(connection, query: str, session_id: str | None) -> int:
    expression = ConversationArchive._normalized_fts_query(query)
    if not expression:
        return 0
    sql = (
        "SELECT m.id FROM conversation_messages_normalized_fts f "
        "JOIN conversation_messages m ON m.id=f.rowid "
        "WHERE conversation_messages_normalized_fts MATCH ?"
    )
    params: list[object] = [expression]
    if session_id:
        sql += " AND m.session_id=?"
        params.append(session_id)
    sql += " ORDER BY m.id DESC LIMIT 8"
    return len(connection.execute(sql, params).fetchall())


def _measure_normalized(connection, query: str, session_id: str | None, iterations: int) -> dict:
    start = time.perf_counter()
    first_count = _run_normalized_query(connection, query, session_id)
    first_ms = (time.perf_counter() - start) * 1000
    samples = []
    counts = []
    for _ in range(iterations):
        start = time.perf_counter()
        counts.append(_run_normalized_query(connection, query, session_id))
        samples.append((time.perf_counter() - start) * 1000)
    return {
        "first_ms": round(first_ms, 3),
        "median_ms": round(statistics.median(samples), 3) if samples else None,
        "p95_ms": round(_percentile(samples, 0.95), 3) if samples else None,
        "iterations": iterations,
        "first_result_count": first_count,
        "stable_result_count": len(set(counts)) <= 1,
        "result_counts": sorted(set(counts)),
    }


def _measure(connection, query: str, session_id: str | None, *, fts: bool, iterations: int) -> dict:
    start = time.perf_counter()
    first_count = _run_query(connection, query, session_id, fts=fts)
    first_ms = (time.perf_counter() - start) * 1000

    samples = []
    counts = []
    for _ in range(iterations):
        start = time.perf_counter()
        counts.append(_run_query(connection, query, session_id, fts=fts))
        samples.append((time.perf_counter() - start) * 1000)

    return {
        "first_ms": round(first_ms, 3),
        "median_ms": round(statistics.median(samples), 3) if samples else None,
        "p95_ms": round(_percentile(samples, 0.95), 3) if samples else None,
        "iterations": iterations,
        "first_result_count": first_count,
        "stable_result_count": len(set(counts)) <= 1,
        "result_counts": sorted(set(counts)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", default=None, help="Restrict measurements to one exact session ID")
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    iterations = max(3, min(100, int(args.iterations)))

    database_path = Path(DB_PATH)
    if not database_path.is_file():
        print(json.dumps({
            "status": "database_not_found",
            "database_path": str(database_path),
            "read_only": True,
        }, ensure_ascii=False, indent=2))
        return 2

    uri = database_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
        }
        if "conversation_messages" not in tables:
            print(json.dumps({
                "status": "conversation_table_not_found",
                "database_path": str(database_path),
                "read_only": True,
            }, ensure_ascii=False, indent=2))
            return 3

        fts_exists = "conversation_messages_fts" in tables
        normalized_fts_exists = (
            "conversation_messages_normalized_fts" in tables
            and "memory_migrations" in tables
            and connection.execute(
                "SELECT 1 FROM memory_migrations WHERE migration_key=?",
                ("normalized_conversation_fts_v1",),
            ).fetchone() is not None
        )
        if args.session_id:
            message_count = connection.execute(
                "SELECT COUNT(*) FROM conversation_messages WHERE session_id=?",
                (args.session_id,),
            ).fetchone()[0]
        else:
            message_count = connection.execute(
                "SELECT COUNT(*) FROM conversation_messages"
            ).fetchone()[0]

        results = {}
        for query in QUERIES:
            results[query] = {
                "fts5": _measure(
                    connection, query, args.session_id,
                    fts=fts_exists, iterations=iterations,
                ) if fts_exists else None,
                "normalized_fts5": _measure_normalized(
                    connection, query, args.session_id, iterations,
                ) if normalized_fts_exists else None,
                "like": _measure(
                    connection, query, args.session_id,
                    fts=False, iterations=iterations,
                ),
            }

        plan = []
        if fts_exists:
            expression = ConversationArchive._fts_query(QUERIES[0])
            plan_sql = (
                "EXPLAIN QUERY PLAN SELECT m.id FROM conversation_messages_fts f "
                "JOIN conversation_messages m ON m.id=f.rowid "
                "WHERE conversation_messages_fts MATCH ?"
            )
            plan = [
                str(tuple(row))
                for row in connection.execute(plan_sql, (expression,)).fetchall()
            ]

        report = {
            "status": "ok",
            "database_path": str(database_path),
            "database_size_bytes": database_path.stat().st_size,
            "session_id": args.session_id,
            "message_count_in_scope": int(message_count),
            "fts5_table_present": fts_exists,
            "normalized_fts5_ready": normalized_fts_exists,
            "sqlite_version": sqlite3.sqlite_version,
            "iterations": iterations,
            "results": results,
            "fts_query_plan": plan,
            "safety": {
                "read_only_connection": True,
                "database_modified": False,
                "index_rebuilt": False,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
