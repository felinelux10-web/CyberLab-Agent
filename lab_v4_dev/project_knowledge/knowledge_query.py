"""
PIE-002A — Knowledge Query Engine

المسؤولية:
- القراءة من قاعدة المعرفة فقط.
- توفير واجهة استعلام موحدة.

لا يقوم بـ:
- تحليل الملفات.
- تحديث قاعدة المعرفة.
- تعديل البيانات.
"""

from .knowledge_store import (
    get_file,
    get_symbols,
    get_dependencies,
)


def file_exists(path):
    """
    يتحقق هل الملف موجود في قاعدة المعرفة.
    """
    return get_file(path) is not None


def get_file_info(path):
    """
    يعيد سجل الملف كاملاً.
    """
    return get_file(path)


def get_file_symbols(path):
    """
    يعيد جميع الرموز الخاصة بالملف.
    """
    file_info = get_file(path)

    if file_info is None:
        return []

    file_id = file_info[0]

    return get_symbols(file_id)


def get_file_dependencies(path):
    """
    يعيد جميع الاعتماديات الخاصة بالملف.
    """
    file_info = get_file(path)

    if file_info is None:
        return []

    file_id = file_info[0]

    return get_dependencies(file_id)


def search_symbol(name):
    """
    يبحث عن رمز داخل قاعدة المعرفة.

    يعيد قائمة بالشكل:
    (path, symbol_name, kind, line)
    """
    import sqlite3
    from .knowledge_store import DB_FILE

    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                files.path,
                symbols.name,
                symbols.kind,
                symbols.line
            FROM symbols
            JOIN files
                ON symbols.file_id = files.id
            WHERE symbols.name = ?
            ORDER BY files.path
        """, (name,))

        return cur.fetchall()

    finally:
        conn.close()


def list_project_files():
    """
    يعيد جميع الملفات الموجودة في قاعدة المعرفة.
    """
    import sqlite3
    from .knowledge_store import DB_FILE

    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT path
            FROM files
            ORDER BY path
        """)

        return [row[0] for row in cur.fetchall()]

    finally:
        conn.close()


def find_files_by_language(language):
    """
    يعيد جميع الملفات الخاصة بلغة معينة.
    """
    import sqlite3
    from .knowledge_store import DB_FILE

    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT path
            FROM files
            WHERE language = ?
            ORDER BY path
        """, (language,))

        return [row[0] for row in cur.fetchall()]

    finally:
        conn.close()


def get_file_relationships(path):
    """
    يعيد العلاقات التي يصدرها ملف.
    """

    import sqlite3
    from .knowledge_store import DB_FILE

    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                target_name,
                relation_type,
                target_kind
            FROM relationships
            WHERE source_file=?
            ORDER BY target_name
            """,
            (path,)
        )

        return cur.fetchall()

    finally:
        conn.close()


def get_related_files(target):
    """
    يعيد الملفات المرتبطة بعنصر معين.
    """

    import sqlite3
    from .knowledge_store import DB_FILE

    conn = sqlite3.connect(DB_FILE)

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                source_file,
                relation_type
            FROM relationships
            WHERE target_name=?
            ORDER BY source_file
            """,
            (target,)
        )

        return cur.fetchall()

    finally:
        conn.close()
