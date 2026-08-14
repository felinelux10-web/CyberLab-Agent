"""
PIE-001D — SQLite Knowledge Store Foundation

المسؤولية:
- إنشاء قاعدة المعرفة
- إدارة الجداول الأساسية فقط

لا يقوم بـ:
- تحليل ملفات
- قراءة AST
- بناء Graph
"""

import sqlite3
import os


DB_FILE = os.path.join(
    os.path.dirname(__file__),
    "knowledge.db"
)


def get_connection():
    return sqlite3.connect(DB_FILE)


def initialize():
    conn = get_connection()
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
        FOREIGN KEY(file_id) REFERENCES files(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dependencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER,
        name TEXT,
        kind TEXT,
        line INTEGER,
        FOREIGN KEY(file_id) REFERENCES files(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT,
        target_name TEXT,
        relation_type TEXT,
        target_kind TEXT,
        UNIQUE(source_file, target_name, relation_type)
    )
    """)

    conn.commit()

if __name__ == "__main__":
    initialize()
    print("✅ Knowledge DB initialized")
    print(DB_FILE)


def _save_file(cur, path, language, file_hash, size, modified):

    cur.execute("""
    INSERT OR REPLACE INTO files
    (path, language, hash, size, modified)
    VALUES (?, ?, ?, ?, ?)
    """,
    (path, language, file_hash, size, modified))

    cur.execute(
        "SELECT id FROM files WHERE path=?",
        (path,)
    )

    file_id = cur.fetchone()[0]

    return file_id


def save_symbols(file_id, symbols):
    conn = get_connection()
    cur = conn.cursor()

    for s in symbols:
        cur.execute("""
        INSERT INTO symbols
        (file_id, name, kind, line)
        VALUES (?, ?, ?, ?)
        """,
        (
            file_id,
            s["name"],
            s["kind"],
            s["line"]
        ))

    conn.commit()
    conn.close()


def save_dependencies(file_id, dependencies):
    conn = get_connection()
    cur = conn.cursor()

    for d in dependencies:
        cur.execute("""
        INSERT INTO dependencies
        (file_id, name, kind, line)
        VALUES (?, ?, ?, ?)
        """,
        (
            file_id,
            d["name"],
            d["kind"],
            d["line"]
        ))

    conn.commit()
    conn.close()


def get_file(path):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM files WHERE path=?",
        (path,)
    )

    result = cur.fetchone()

    conn.close()

    return result


def get_symbols(file_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT name, kind, line FROM symbols WHERE file_id=?",
        (file_id,)
    )

    result = cur.fetchall()

    conn.close()

    return result


def get_dependencies(file_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT name, kind, line FROM dependencies WHERE file_id=?",
        (file_id,)
    )

    result = cur.fetchall()

    conn.close()

    return result


def store_analysis(result,
                   file_hash="",
                   size=0,
                   modified=""):
    conn = get_connection()

    try:
        cur = conn.cursor()

        file_id = _save_file(
            cur,
            result.file_path,
            result.language,
            file_hash,
            size,
            modified
        )

        cur.execute(
            "DELETE FROM symbols WHERE file_id=?",
            (file_id,)
        )

        cur.execute(
            "DELETE FROM dependencies WHERE file_id=?",
            (file_id,)
        )

        conn.commit()

        save_symbols(
            file_id,
            result.symbols
        )

        save_dependencies(
            file_id,
            result.dependencies
        )

        return file_id

    finally:
        conn.close()


def save_relationships(relationships):
    conn = get_connection()
    cur = conn.cursor()

    for r in relationships:
        cur.execute(
            """
            INSERT OR IGNORE INTO relationships
            (source_file, target_name, relation_type, target_kind)
            VALUES (?, ?, ?, ?)
            """,
            (
                r.source,
                r.target,
                r.relation_type,
                r.target_kind
            )
        )

    conn.commit()
    conn.close()
