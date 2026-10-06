# CyberLab Agent v4.8
# memory/session_state.py

import json
import os
from datetime import datetime

def _session_file() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("session_state.json")


MAX_RECENT_SESSIONS = 5


def _archive_file() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("session_archive.json")


def _append_recent_archive(data: dict) -> None:
    """Keep compact summaries only; never archive the bounded transcript."""
    path = _archive_file()
    try:
        with open(path, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = []
    if not isinstance(archive, list):
        archive = []
    summary = {
        key: data.get(key)
        for key in (
            "session_id", "timestamp", "active_goal", "completed_work",
            "next_step", "last_files", "decisions", "open_questions", "project_root",
        )
        if key in data
    }
    if archive and archive[-1].get("session_id") == summary.get("session_id"):
        archive[-1] = summary
    else:
        archive.append(summary)
    archive = archive[-MAX_RECENT_SESSIONS:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def get_recent_sessions() -> list:
    try:
        with open(_archive_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data[-MAX_RECENT_SESSIONS:] if isinstance(data, list) else []
    except Exception:
        return []

def save_session(active_goal: str = None, completed: list = None,
                 next_step: str = None, last_files: list = None,
                 version: str = "unknown", *, dialogue_state: dict = None,
                 context_state: dict = None, project_root: str = None,
                 decisions: list = None, open_questions: list = None):
    data = {
        "session_id"   : datetime.now().strftime("%Y%m%d_%H%M%S"),
        "version"      : version,
        "timestamp"    : datetime.now().isoformat(),
        "active_goal"  : active_goal or "",
        "completed_work": completed or [],
        "next_step"    : next_step or "",
        "last_files"   : last_files or [],
    }
    if dialogue_state is not None:
        data["dialogue_state"] = dialogue_state
    if context_state is not None:
        data["context_state"] = context_state
    if project_root:
        data["project_root"] = project_root
    if decisions is not None:
        data["decisions"] = list(decisions)
    if open_questions is not None:
        data["open_questions"] = list(open_questions)
    # المسار الرئيسي: project_knowledge (Single Writer)
    # الـ fallback: كتابة مباشرة فقط عند فشل الاستيراد (استثناء معروف)
    try:
        from lab_v4_dev.awareness.project_knowledge import save_session as pk_save
        pk_save(data)
    except Exception:
        # FALLBACK — يُستخدم فقط إذا تعذر استيراد project_knowledge
        path = _session_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    _append_recent_archive(data)
    return data


def save_recoverable_checkpoint(*, active_goal: str = "", next_step: str = "",
                                last_files: list = None, version: str = "unknown",
                                dialogue_state: dict = None, context_state: dict = None,
                                project_root: str = None, decisions: list = None,
                                open_questions: list = None) -> dict:
    """Persist a bounded checkpoint without replacing existing work metadata."""
    existing = load_session()
    data = dict(existing or {})
    data.update({
        "session_id": data.get("session_id") or datetime.now().strftime("%Y%m%d_%H%M%S"),
        "timestamp": datetime.now().isoformat(),
        "version": version or data.get("version", "unknown"),
        "active_goal": active_goal or data.get("active_goal", ""),
        "next_step": next_step or data.get("next_step", ""),
        "last_files": list(last_files or data.get("last_files", [])),
    })
    if dialogue_state is not None:
        data["dialogue_state"] = dialogue_state
    if context_state is not None:
        data["context_state"] = context_state
    if project_root:
        data["project_root"] = project_root
    if decisions is not None:
        data["decisions"] = list(decisions)
    if open_questions is not None:
        data["open_questions"] = list(open_questions)
    try:
        from lab_v4_dev.awareness.project_knowledge import save_session as pk_save
        pk_save(data)
    except Exception:
        path = _session_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    _append_recent_archive(data)
    return data

def load_session() -> dict:
    try:
        from lab_v4_dev.awareness.project_knowledge import get_session_state
        return get_session_state()
    except:
        return {}

def clear_session():
    path = _session_file()
    if os.path.exists(path):
        os.remove(path)
