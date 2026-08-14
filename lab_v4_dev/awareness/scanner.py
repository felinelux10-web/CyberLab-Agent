# CyberLab Agent v4.0
# awareness/scanner.py

import os
import hashlib
from lab_v4_dev.memory.db import Database
from lab_v4_dev.core.project_context import get_active_project_root

def hash_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    except Exception:
        return ""

def extract_summary(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[:20]).strip()
    except Exception:
        return ""

def scan_file(path: str, db: Database) -> dict:
    current_hash = hash_file(path)
    stored = db.fetchone(
        "SELECT * FROM project_map WHERE file_path=?",
        (path,)
    )

    if stored and stored["file_hash"] == current_hash:
        return {"status": "unchanged", "path": path}

    summary = extract_summary(path)
    now = db.now()

    if stored:
        db.execute(
            """UPDATE project_map
               SET file_hash=?, summary=?, last_scanned=?
               WHERE file_path=?""",
            (current_hash, summary, now, path)
        )
    else:
        db.execute(
            """INSERT INTO project_map
               (file_path, file_hash, summary, last_scanned)
               VALUES (?, ?, ?, ?)""",
            (path, current_hash, summary, now)
        )

    return {"status": "updated", "path": path, "hash": current_hash[:16]}

def scan_directory(directory: str | None = None, db: Database = None, extensions: list = None) -> dict:
    if directory is None:
        directory = get_active_project_root()

    if db is None:
        db = Database()
        db.connect()

    if extensions is None:
        extensions = [".py", ".md", ".yaml", ".sql", ".txt"]

    results = {"updated": 0, "unchanged": 0, "errors": 0}

    for root, dirs, files in os.walk(directory):
        # تجاهل مجلدات غير ضرورية
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "archives", "cache", "stable", "releases", "project_indices", "workspace"]]

        for file in files:
            if not any(file.endswith(ext) for ext in extensions):
                continue

            path = os.path.join(root, file)
            try:
                result = scan_file(path, db)
                if result["status"] == "updated":
                    results["updated"] += 1
                else:
                    results["unchanged"] += 1
            except Exception:
                results["errors"] += 1

    return results
