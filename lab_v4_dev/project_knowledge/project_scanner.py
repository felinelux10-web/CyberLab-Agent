# CyberLab Agent — Project Intelligence Engine
# project_knowledge/project_scanner.py
#
# PIE-001A: Project Scanner Foundation
# المسؤولية: فحص ملفات المشروع وبناء inventory.json فقط.
# ممنوع: تحليل imports, AST, دوال, كلاسات, أو dependency graph.
# مستقل تماماً عن بقية الوكيل.

import os
import json
from lab_v4_dev.project_registry.project_loader import get_active_project
import time
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from lab_v4_dev.project_knowledge.language_registry import get_language, is_analyzable
from lab_v4_dev.project_knowledge.analyzer_registry import supports_extension

SKIP_DIRS = {
    "stable", "snapshots", "__pycache__", ".git",
    "venv", "cache", ".venv", "node_modules", "dist", "build",
    "project_knowledge",
}

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "inventory.json")


def scan(project_root: str) -> dict:
    """فحص المشروع وإرجاع inventory كاملاً"""
    inventory = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path  = os.path.relpath(full_path, project_root)
            ext       = os.path.splitext(fname)[1].lower()
            try:
                stat = os.stat(full_path)
                size = stat.st_size
                last_modified = time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime))
            except Exception:
                size, last_modified = 0, "?"
            inventory.append({
                "path"         : rel_path,
                "filename"     : fname,
                "extension"    : ext,
                "file_type"    : "file",
                "language"     : get_language(ext),
                "size"         : size,
                "last_modified": last_modified,
                "analyzable"   : is_analyzable(ext),
                "analyzer"     : supports_extension(ext),
            })
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "project_root": project_root,
        "total_files" : len(inventory),
        "files"       : inventory,
    }


def run(project_root: str = None) -> dict:
    """نقطة الدخول الرسمية"""
    if project_root is None:
        active = get_active_project()
        if active:
            project_root = active["root"]
        else:
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), ".."))
    result = scan(project_root)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    r = run()
    print(f"✅ inventory.json: {r['total_files']} ملف")
    print(f"📁 {OUTPUT_FILE}")

