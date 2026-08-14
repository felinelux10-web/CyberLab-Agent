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

from .knowledge_store import DB_FILE
import sqlite3


def get_neighbors(target):
    """
    يعيد العناصر المرتبطة بعنصر معين.
    """

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
            (target, target)
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

        # تحويل المسار إلى صيغة module: lab_v4_dev/core/agent.py → lab_v4_dev.core.agent
        def _to_module(p):
            if p.endswith(".py"):
                p = p[:-3]
            return p.replace("/", ".").replace("\\", ".")
        
        target_module = _to_module(target) if "/" in target or "\\" in target else target
        
        cur.execute(
            """
            SELECT
                source_file
            FROM relationships
            WHERE target_name = ?
               OR target_name = ?
            ORDER BY source_file
            """,
            (target, target_module)
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
            (source,)
        )

        return [
            row[0]
            for row in cur.fetchall()
        ]

    finally:
        conn.close()
