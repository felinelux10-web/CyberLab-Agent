# CyberLab Agent v4.8
# memory/session_state.py

import json
import os
from datetime import datetime

SESSION_FILE = "project_data/session_state.json"

def save_session(active_goal: str = None, completed: list = None,
                 next_step: str = None, last_files: list = None,
                 version: str = "unknown"):
    data = {
        "session_id"   : datetime.now().strftime("%Y%m%d_%H%M%S"),
        "version"      : version,
        "timestamp"    : datetime.now().isoformat(),
        "active_goal"  : active_goal or "",
        "completed_work": completed or [],
        "next_step"    : next_step or "",
        "last_files"   : last_files or [],
    }
    # المسار الرئيسي: project_knowledge (Single Writer)
    # الـ fallback: كتابة مباشرة فقط عند فشل الاستيراد (استثناء معروف)
    try:
        from lab_v4_dev.awareness.project_knowledge import save_session as pk_save
        pk_save(data)
    except Exception:
        # FALLBACK — يُستخدم فقط إذا تعذر استيراد project_knowledge
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def load_session() -> dict:
    try:
        from lab_v4_dev.awareness.project_knowledge import get_session_state
        return get_session_state()
    except:
        return {}

def clear_session():
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
