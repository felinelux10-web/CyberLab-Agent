# CyberLab Agent v4.6
# awareness/state_reader.py

import json, os
from datetime import datetime

STATE_FILE = "lab_v4/cache/project_state.json"

def load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get(key: str, default=None):
    return load().get(key, default)

def update(key: str, value):
    state = load()
    state[key] = value
    state["last_updated"] = datetime.now().isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def add_modified_file(file_path: str):
    state = load()
    files = state.get("last_modified_files", [])
    if file_path not in files:
        files.insert(0, file_path)
    state["last_modified_files"] = files[:10]
    state["last_updated"] = datetime.now().isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def summary() -> str:
    s = load()
    return (
        f"المشروع: {s.get('project_name')} v{s.get('version')} | "
        f"ملفات: {s.get('files_count')} | "
        f"مراحل مكتملة: {len(s.get('completed_phases',[]))} | "
        f"آخر تحديث: {s.get('last_updated','?')[:10]}"
    )
