# CyberLab Agent v4.0
# awareness/model_builder.py

from lab_v4_dev.memory.db import Database
from lab_v4_dev.core.project_context import get_active_project_root

def build_model(db: Database) -> dict:
    files = db.fetchall("SELECT * FROM project_map ORDER BY last_scanned DESC")

    model = {
        "total_files": len(files),
        "python_files": [],
        "config_files": [],
        "other_files": [],
    }

    for f in files:
        path = f["file_path"]

        root = get_active_project_root().replace("\\", "/")
        norm = path.replace("\\", "/")
        if norm.startswith(root):
            path = norm[len(root):].lstrip("/")

        root = get_active_project_root().replace("\\", "/")
        norm = path.replace("\\", "/")
        if norm.startswith(root):
            path = norm[len(root):].lstrip("/")
        entry = {
            "path"   : path,
            "hash"   : f["file_hash"],
            "scanned": f["last_scanned"],
        }
        if path.endswith(".py"):
            model["python_files"].append(entry)
        elif path.endswith((".yaml", ".sql", ".md")):
            model["config_files"].append(entry)
        else:
            model["other_files"].append(entry)

    return model

def get_file_context(path: str, db: Database) -> dict | None:
    return db.fetchone(
        "SELECT * FROM project_map WHERE file_path=?",
        (path,)
    )

def find_changed_files(db: Database, since: str) -> list:
    return db.fetchall(
        "SELECT * FROM project_map WHERE last_scanned > ? ORDER BY last_scanned DESC",
        (since,)
    )
