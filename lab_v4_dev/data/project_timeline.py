# CyberLab Agent v4.8
# data/project_timeline.py

import json
import os
from datetime import datetime

TIMELINE_FILE = "project_data/project_timeline.json"

def load_timeline() -> list:
    try:
        with open(TIMELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_timeline(timeline: list):
    os.makedirs(os.path.dirname(TIMELINE_FILE), exist_ok=True)
    with open(TIMELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)

def add_event(version: str, event: str, details: str = ""):
    timeline = load_timeline()
    timeline.append({
        "date"   : datetime.now().strftime("%Y-%m-%d"),
        "version": version,
        "event"  : event,
        "details": details,
    })
    save_timeline(timeline)

def get_version_events(version: str) -> list:
    return [e for e in load_timeline() if e["version"] == version]

def get_full_history() -> str:
    timeline = load_timeline()
    if not timeline:
        return "لا يوجد تاريخ مسجل بعد"
    lines = ["=== Project Timeline ==="]
    current_v = None
    for e in timeline:
        if e["version"] != current_v:
            current_v = e["version"]
            lines.append(f"\n{current_v}:")
        lines.append(f"  [{e['date']}] {e['event']}")
        if e.get("details"):
            lines.append(f"    → {e['details']}")
    return "\n".join(lines)

def init_timeline():
    """يبني timeline من releases/ الموجودة"""
    timeline = load_timeline()
    if timeline:
        return  # موجود بالفعل

    history = [
        ("v4.0", "Infrastructure + Memory + Recovery"),
        ("v4.1", "CLI Commands + help/status/ls/health"),
        ("v4.2", "Executor + Monitor + Budget"),
        ("v4.3", "Planner + Step Builder"),
        ("v4.4", "Awareness + Project Memory"),
        ("v4.5", "Intent System + Fuzzy Normalizer"),
        ("v4.6", "Groq Integration + Context Binding"),
        ("v4.7", "Project Awareness + Dependency Map + Grounded Prompts"),
        ("v4.8", "Continuity Layer — in progress"),
    ]
    for version, event in history:
        timeline.append({
            "date"   : "2026-06-01",
            "version": version,
            "event"  : event,
            "details": "",
        })
    save_timeline(timeline)
