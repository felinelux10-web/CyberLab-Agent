"""
PIE-002C — Graph Query Engine

المسؤولية:
- استعلام شبكة العلاقات.
- البحث عن العناصر المرتبطة.

لا يقوم بـ:
- تعديل قاعدة البيانات.
- تحليل الملفات.
- إنشاء علاقات جديدة.
"""

from .knowledge_store import DB_FILE, canonical_file_path
import os
import sqlite3


def _canonical_source_path(value):
    """Normalize path-like source identifiers to the store identity."""
    text = str(value or "").strip()
    if not text:
        return text
    if text.endswith(".py") or "/" in text or "\\" in text or os.path.isabs(text):
        return canonical_file_path(text)
    return text


def _module_name(path):
    """Convert a canonical Python path to its import-module spelling."""
    text = str(path or "")
    if text.endswith(".py"):
        text = text[:-3]
    return text.replace("/", ".").replace("\\", ".")


def get_neighbors(target):
    """
    يعيد العناصر المرتبطة بعنصر معين.
    """

    normalized_target = _canonical_source_path(target)
    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                source_file,
                relation_type,
                target_name
            FROM relationships
            WHERE source_file = ?
               OR target_name = ?
            """,
            (normalized_target, target)
        )

        return cur.fetchall()

    finally:
        conn.close()


def get_importers(target):
    """
    يعيد الملفات التي تعتمد على عنصر معين.
    """

    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        # Accept a project-relative path, absolute path inside the project,
        # or an import/module name while querying the same canonical store.
        normalized_target = _canonical_source_path(target)
        target_module = _module_name(normalized_target) if normalized_target.endswith(".py") else target
        
        cur.execute(
            """
            SELECT
                source_file
            FROM relationships
            WHERE target_name = ?
               OR target_name = ?
            ORDER BY source_file
            """,
            (normalized_target, target_module)
        )

        return [
            row[0]
            for row in cur.fetchall()
        ]

    finally:
        conn.close()


def get_dependencies_of(source):
    """
    يعيد ما يستخدمه ملف معين.
    """

    normalized_source = _canonical_source_path(source)
    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                target_name
            FROM relationships
            WHERE source_file = ?
            ORDER BY target_name
            """,
            (normalized_source,)
        )

        return [
            row[0]
            for row in cur.fetchall()
        ]

    finally:
        conn.close()
