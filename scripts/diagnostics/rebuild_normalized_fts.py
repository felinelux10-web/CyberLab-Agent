#!/usr/bin/env python3
"""Explicitly rebuild the derived normalized FTS index; source messages are untouched."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from lab_v4_dev.memory.db import Database
from lab_v4_dev.memory.conversation_archive import ConversationArchive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that the derived search index will be rebuilt",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    if not args.confirm:
        parser.error("pass --confirm to rebuild the derived normalized FTS index")

    database = Database()
    try:
        database.connect()
        archive = ConversationArchive(database)
        result = archive.rebuild_normalized_search_index(
            batch_size=max(1, min(200, int(args.batch_size))),
        )
        print(json.dumps({
            **result,
            "source_messages_modified": False,
            "legacy_fts_modified": False,
            "database_path": str(database.__class__.__module__),
        }, ensure_ascii=False, indent=2))
        return 0 if result.get("complete") else 2
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
