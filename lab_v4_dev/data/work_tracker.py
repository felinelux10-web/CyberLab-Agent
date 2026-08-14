# CyberLab Agent v4.7
# data/work_tracker.py

import json
import os

ROADMAP_FILE = "project_data/roadmap.json"

def load_roadmap() -> dict:
    try:
        from lab_v4_dev.awareness.project_knowledge import get_roadmap
        return get_roadmap()
    except:
        return {}

def save_roadmap(data: dict):
    from lab_v4_dev.awareness.project_knowledge import save_roadmap as pk_save_roadmap
    pk_save_roadmap(data)

def get_status() -> dict:
    r = load_roadmap()
    return {
        "version"      : r.get("version", "?"),
        "current_focus": r.get("current_focus", "?"),
        "completed"    : r.get("completed", []),
        "active"       : r.get("active", []),
        "planned"      : r.get("planned", []),
        "blocked"      : r.get("blocked", []),
        "deferred"     : r.get("deferred", []),
    }

def get_next_task() -> str:
    r = load_roadmap()
    active  = r.get("active", [])
    planned = r.get("planned", [])
    if active:  return active[0]
    if planned: return planned[0]
    return "لا توجد مهام مخططة"

def complete_task(task: str) -> bool:
    r = load_roadmap()
    for cat in ["active", "planned"]:
        if task in r.get(cat, []):
            r[cat].remove(task)
            r.setdefault("completed", []).append(task)
            save_roadmap(r)
            return True
    return False

def add_task(task: str, category: str = "planned") -> bool:
    r = load_roadmap()
    if task not in r.get(category, []):
        r.setdefault(category, []).append(task)
        save_roadmap(r)
        return True
    return False

def get_remaining() -> list:
    r = load_roadmap()
    return r.get("active", []) + r.get("planned", [])
