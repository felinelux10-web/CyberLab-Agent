"""
P09 — Canonical SQLite Knowledge Store.

Responsibilities:
    - Persist project knowledge.
    - Maintain transactional integrity.
    - Own the knowledge database schema.

Does NOT:
    - analyze source files
    - parse AST
    - build relationships
    - answer semantic/project queries
"""

from __future__ import annotations
from pathlib import Path

import os
import sqlite3


DB_FILE = os.path.join(
    os.path.dirname(__file__),
    "knowledge.db",
)


def get_active_project_root():
    """
    Return the canonical active project root.

    project_context is the single source of truth for project identity.
    """
    from lab_v4_dev.core.project_context import get_active_project_root

    return Path(get_active_project_root()).resolve()


def canonical_file_path(path):
    """
    Convert a filesystem path into the canonical project-relative POSIX
    identity used by the knowledge store.

    Absolute paths must belong to the active project.
    Relative paths are interpreted relative to the active project root.

    Examples:
        /project/main.py -> main.py
        /project/lab_v4_dev/core/agent.py
            -> lab_v4_dev/core/agent.py

    Raises:
        ValueError: if the path escapes the active project.
    """
    root = get_active_project_root()

    raw = Path(path)

    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (root / raw).resolve()

    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Path is outside active project: {path}"
        ) from exc

    return relative.as_posix()


def canonical_relationship_source(path):
    """
    Canonicalize a relationship source using the same file identity
    contract as the files table.
    """
    return canonical_file_path(path)


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize():
    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            language TEXT,
            hash TEXT,
            size INTEGER,
            modified TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            name TEXT,
            kind TEXT,
            line INTEGER,
            FOREIGN KEY(file_id)
                REFERENCES files(id)
                ON DELETE CASCADE
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            name TEXT,
            kind TEXT,
            line INTEGER,
            FOREIGN KEY(file_id)
                REFERENCES files(id)
                ON DELETE CASCADE
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            target_name TEXT,
            relation_type TEXT,
            target_kind TEXT,
            UNIQUE(
                source_file,
                target_name,
                relation_type
            )
        )
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_symbols_file_id
        ON symbols(file_id)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_symbols_name
        ON symbols(name)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_dependencies_file_id
        ON dependencies(file_id)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_relationships_source
        ON relationships(source_file)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_relationships_target
        ON relationships(target_name)
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def _save_file(
    cur,
    path,
    language,
    file_hash,
    size,
    modified,
):
    path = canonical_file_path(path)

    cur.execute(
        """
        INSERT INTO files
            (path, language, hash, size, modified)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            language = excluded.language,
            hash = excluded.hash,
            size = excluded.size,
            modified = excluded.modified
        """,
        (
            path,
            language,
            file_hash,
            size,
            modified,
        ),
    )

    cur.execute(
        "SELECT id FROM files WHERE path=?",
        (path,),
    )

    row = cur.fetchone()

    if row is None:
        raise RuntimeError(
            f"Failed to obtain file id for: {path}"
        )

    return row[0]


def save_symbols(file_id, symbols, *, connection=None):
    owns_connection = connection is None
    conn = connection or get_connection()

    try:
        cur = conn.cursor()

        for symbol in symbols:
            cur.execute(
                """
                INSERT INTO symbols
                    (file_id, name, kind, line)
                VALUES (?, ?, ?, ?)
                """,
                (
                    file_id,
                    symbol["name"],
                    symbol["kind"],
                    symbol["line"],
                ),
            )

        if owns_connection:
            conn.commit()

    except Exception:
        if owns_connection:
            conn.rollback()
        raise

    finally:
        if owns_connection:
            conn.close()


def save_dependencies(
    file_id,
    dependencies,
    *,
    connection=None,
):
    owns_connection = connection is None
    conn = connection or get_connection()

    try:
        cur = conn.cursor()

        for dependency in dependencies:
            cur.execute(
                """
                INSERT INTO dependencies
                    (file_id, name, kind, line)
                VALUES (?, ?, ?, ?)
                """,
                (
                    file_id,
                    dependency["name"],
                    dependency["kind"],
                    dependency["line"],
                ),
            )

        if owns_connection:
            conn.commit()

    except Exception:
        if owns_connection:
            conn.rollback()
        raise

    finally:
        if owns_connection:
            conn.close()


def get_file(path):
    path = canonical_file_path(path)

    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                path,
                language,
                hash,
                size,
                modified
            FROM files
            WHERE path=?
            """,
            (path,),
        )

        return cur.fetchone()

    finally:
        conn.close()


def get_symbols(file_id):
    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT name, kind, line
            FROM symbols
            WHERE file_id=?
            ORDER BY line, name
            """,
            (file_id,),
        )

        return cur.fetchall()

    finally:
        conn.close()


def get_dependencies(file_id):
    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT name, kind, line
            FROM dependencies
            WHERE file_id=?
            ORDER BY line, name
            """,
            (file_id,),
        )

        return cur.fetchall()

    finally:
        conn.close()


def store_analysis(
    result,
    file_hash="",
    size=0,
    modified="",
):
    """
    Atomically persist one complete analysis result.

    The file record, symbols and dependencies are committed
    as one transaction.
    """

    conn = get_connection()

    try:
        cur = conn.cursor()

        file_id = _save_file(
            cur,
            result.file_path,
            result.language,
            file_hash,
            size,
            modified,
        )

        cur.execute(
            "DELETE FROM symbols WHERE file_id=?",
            (file_id,),
        )

        cur.execute(
            "DELETE FROM dependencies WHERE file_id=?",
            (file_id,),
        )

        save_symbols(
            file_id,
            result.symbols,
            connection=conn,
        )

        save_dependencies(
            file_id,
            result.dependencies,
            connection=conn,
        )

        conn.commit()

        return file_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def save_relationships(relationships):
    """
    Atomically persist a relationship batch.
    """

    conn = get_connection()

    try:
        cur = conn.cursor()

        for relationship in relationships:
            source_file = canonical_relationship_source(
                relationship.source
            )

            cur.execute(
                """
                INSERT INTO relationships
                    (
                        source_file,
                        target_name,
                        relation_type,
                        target_kind
                    )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(
                    source_file,
                    target_name,
                    relation_type
                )
                DO UPDATE SET
                    target_kind = excluded.target_kind
                """,
                (
                    source_file,
                    relationship.target,
                    relationship.relation_type,
                    relationship.target_kind,
                ),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
