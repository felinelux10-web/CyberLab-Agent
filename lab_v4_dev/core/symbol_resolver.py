"""
symbol_resolver.py — v5.9.10.E
يحدد الملف والدالة المطلوبة من طلب المستخدم
"""
import os
import re
from lab_v4_dev.core.surgical_editor import list_symbols
from lab_v4_dev.core.project_context import get_active_project_root


def resolve(raw: str, target: str = "") -> dict:
    """
    يحلل طلب المستخدم ويعيد:
    {
      "file": "lab_v4_dev/core/cleaner.py",
      "symbol": "get_free_space_mb",
      "instruction": "أضف تعليق"
    }
    """
    root = get_active_project_root()

    # 1. إذا ذكر ملف محدد كـ target
    if target and target.endswith(".py"):
        file_path = _resolve_path(target, root)
        symbol = _extract_symbol_name(raw, file_path)
        return {"file": file_path, "symbol": symbol,
                "instruction": raw, "found": bool(file_path)}

    # 2. ابحث عن اسم ملف في النص
    py_match = re.search(r'[\w./]+\.py', raw)
    if py_match:
        file_path = _resolve_path(py_match.group(0), root)
        symbol = _extract_symbol_name(raw, file_path)
        return {"file": file_path, "symbol": symbol,
                "instruction": raw, "found": bool(file_path)}

    # 3. ابحث عن اسم دالة في كل ملفات المشروع
    symbol_name = _find_symbol_in_project(raw, root)
    if symbol_name:
        return {"file": symbol_name["file"], "symbol": symbol_name["symbol"],
                "instruction": raw, "found": True}

    return {"file": "", "symbol": "", "instruction": raw, "found": False}


def _resolve_path(path: str, root: str) -> str:
    """يحول المسار النسبي لمسار كامل"""
    if os.path.isabs(path):
        return path if os.path.exists(path) else ""
    candidates = [
        os.path.join(root, path),
        os.path.expanduser(f"~/{path}"),
        path,
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""


def _extract_symbol_name(raw: str, file_path: str) -> str:
    """يحاول إيجاد اسم دالة مذكورة في النص"""
    if not file_path or not os.path.exists(file_path):
        return ""
    symbols = list_symbols(file_path)
    for s in symbols:
        if s["name"] in raw:
            return s["name"]
    return ""


def _find_symbol_in_project(raw: str, root: str) -> dict:
    """يبحث عن دالة بالاسم في كل ملفات المشروع"""
    src = os.path.join(root, "lab_v4_dev")
    if not os.path.exists(src):
        src = root
    for dirpath, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in
                   ["__pycache__", "stable", "releases", "workspace"]]
        for f in files:
            if not f.endswith(".py"):
                continue
            fp = os.path.join(dirpath, f)
            try:
                symbols = list_symbols(fp)
                for s in symbols:
                    if s["name"] in raw:
                        return {"file": fp, "symbol": s["name"]}
            except:
                pass
    return {}
