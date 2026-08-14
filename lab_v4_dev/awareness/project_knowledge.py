# CyberLab Agent v5.9.8.B
# awareness/project_knowledge.py
# Single Source of Truth لحالة المشروع

import json
import os
import yaml

BASE = os.path.expanduser("~/cyberlab_agent")
DATA = os.path.join(BASE, "project_data")

# ─── Cache Layer ───
import time as _time

_cache = {}
_cache_state = {
    "loaded"      : False,
    "dirty"       : False,
    "loaded_at"   : None,
    "last_refresh": None,
    "last_write"  : None,
    "version"     : 0,
}

# ─── Event Log ───
_events = []
_MAX_EVENTS = 100

def _emit(event: str, payload: dict = None):
    """تسجيل حدث داخلي"""
    global _events
    _events.append({
        "event"  : event,
        "time"   : _time.time(),
        "payload": payload or {},
    })
    if len(_events) > _MAX_EVENTS:
        _events = _events[-_MAX_EVENTS:]

def get_events() -> list:
    """إرجاع جميع الأحداث المسجلة"""
    return list(_events)

def get_last_event() -> dict:
    """إرجاع آخر حدث"""
    return _events[-1] if _events else {}

def clear_events():
    """مسح سجل الأحداث"""
    global _events
    _events = []

def _load_all():
    """تحميل جميع الملفات مرة واحدة عند أول استدعاء"""
    global _cache, _cache_state
    if _cache_state["loaded"]:
        return
    for filename in ["roadmap.json", "session_state.json",
                     "project_history.json", "version_history.json"]:
        fpath = os.path.join(DATA, filename)
        if os.path.exists(fpath):
            try:
                with open(fpath, encoding="utf-8") as f:
                    _cache[filename] = json.load(f)
            except:
                _cache[filename] = {}
        else:
            _cache[filename] = {}
    _cache_state["loaded"]    = True
    _cache_state["dirty"]     = False
    _cache_state["loaded_at"] = _time.time()

def _load(filename):
    _load_all()
    return _cache.get(filename, {})

def refresh_cache():
    """إعادة تحميل جميع الملفات من القرص وتحديث Cache"""
    global _cache, _cache_state
    _cache_state["loaded"] = False
    _cache = {}
    _load_all()
    _cache_state["last_refresh"] = _time.time()
    _cache_state["dirty"]        = False

def reload_file(filename: str):
    """إعادة تحميل ملف واحد فقط من القرص"""
    global _cache
    _load_all()
    fpath = os.path.join(DATA, filename)
    if os.path.exists(fpath):
        try:
            with open(fpath, encoding="utf-8") as f:
                _cache[filename] = json.load(f)
        except:
            _cache[filename] = {}
    else:
        _cache[filename] = {}

def invalidate_cache():
    """إبطال الـ Cache وإجبار إعادة التحميل عند الطلب التالي"""
    global _cache, _cache_state
    _cache = {}
    _cache_state["loaded"] = False
    _cache_state["dirty"]  = False

def cache_status() -> dict:
    """معلومات كاملة عن حالة Cache"""
    return {
        "loaded"      : _cache_state["loaded"],
        "dirty"       : _cache_state["dirty"],
        "loaded_at"   : _cache_state["loaded_at"],
        "last_refresh": _cache_state["last_refresh"],
        "last_write"  : _cache_state["last_write"],
        "version"     : _cache_state["version"],
        "files"       : list(_cache.keys()),
    }

def cache_version() -> int:
    return _cache_state["version"]

def cache_is_dirty() -> bool:
    return _cache_state["dirty"]

def cache_loaded_at() -> float:
    return _cache_state["loaded_at"]

def is_cache_valid(max_age: float = None) -> bool:
    """هل الـ Cache صالح؟ max_age بالثواني"""
    if not _cache_state["loaded"]:
        return False
    if _cache_state["dirty"]:
        return False
    if max_age and _cache_state["loaded_at"]:
        return (_time.time() - _cache_state["loaded_at"]) < max_age
    return True

def get_current_version() -> str:
    try:
        from lab_v4_dev.awareness.release_analyzer import get_available_versions
        versions = get_available_versions()
        if versions:
            return versions[-1]
    except:
        pass
    try:
        ref = yaml.safe_load(open(os.path.join(BASE, "lab_v4_dev/configs/MASTER_REF.yaml"), encoding="utf-8"))
        return ref.get("project", {}).get("version", "?")
    except:
        return _load("roadmap.json").get("version", "?")

def get_roadmap() -> dict:
    return _load("roadmap.json")

def get_session_state() -> dict:
    return _load("session_state.json")

def get_project_history() -> dict:
    return _load("project_history.json")

def get_version_history() -> dict:
    return _load("version_history.json")

def get_project_state() -> dict:
    roadmap = get_roadmap()
    session = get_session_state()
    version = get_current_version()
    history = get_project_history()
    return {
        "version"       : version,
        "current_focus" : roadmap.get("current_focus", "?"),
        "active"        : roadmap.get("active", []),
        "planned"       : roadmap.get("planned", []),
        "completed_count": len(roadmap.get("completed", [])),
        "last_project"  : history.get("last_project", "?"),
        "last_goal"     : session.get("active_goal", "?"),
        "last_step"     : session.get("next_step", "?"),
        "last_files"    : session.get("last_files", []),
    }

def get_open_issues() -> list:
    return get_roadmap().get("planned", [])

def get_completed() -> list:
    return get_roadmap().get("completed", [])

def summary() -> str:
    s = get_project_state()
    lines = [
        f"الإصدار: {s['version']}",
        f"التركيز: {s['current_focus']}",
        f"نشط: {chr(10).join(s['active']) or 'لا شيء'}",
        f"مكتمل: {s['completed_count']} ميزة",
        f"آخر مشروع: {s['last_project']}",
        f"آخر هدف: {s['last_goal']}",
    ]
    return chr(10).join(lines)

def get_version() -> str:
    return get_current_version()

def get_current_focus() -> str:
    return get_roadmap().get("current_focus", "?")

def get_active() -> list:
    return get_roadmap().get("active", [])

def get_planned() -> list:
    return get_roadmap().get("planned", [])

def get_blocked() -> list:
    return get_roadmap().get("blocked", [])

def get_last_project() -> str:
    return get_project_history().get("last_project", "?")

def get_last_project_root() -> str:
    return get_project_history().get("last_root", "?")

def get_project_history_list() -> list:
    return get_project_history().get("history", [])

def get_last_session() -> dict:
    return get_session_state()

def get_last_goal() -> str:
    return get_session_state().get("active_goal", "?")

def get_last_step() -> str:
    return get_session_state().get("next_step", "?")

def get_last_files() -> list:
    return get_session_state().get("last_files", [])

def get_latest_release() -> str:
    vh = get_version_history()
    releases = vh.get("releases", [])
    if releases:
        return releases[-1].get("version", "?")
    return get_current_version()

def get_release(version: str) -> dict:
    vh = get_version_history()
    for r in vh.get("releases", []):
        if r.get("version") == version:
            return r
    return {}

def search_versions(keyword: str) -> list:
    vh = get_version_history()
    results = []
    for r in vh.get("releases", []):
        if keyword.lower() in r.get("version", "").lower() or keyword.lower() in r.get("summary", "").lower():
            results.append(r)
    return results

def project_summary() -> str:
    return summary()

# ─── Write Layer ───

def _write(filename: str, data: dict):
    """يكتب إلى الملف ويحدث Cache و_cache_state"""
    global _cache, _cache_state
    _load_all()
    fpath = os.path.join(DATA, filename)
    os.makedirs(DATA, exist_ok=True)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _cache[filename]           = data
    _cache_state["last_write"] = _time.time()
    _cache_state["dirty"]      = False
    _cache_state["version"]   += 1

def save_roadmap(data: dict):
    """حفظ roadmap وتحديث Cache"""
    _write("roadmap.json", data)
    _emit("roadmap_updated", {"keys": list(data.keys()) if isinstance(data, dict) else []})

def save_session(data: dict):
    """حفظ session_state وتحديث Cache"""
    _write("session_state.json", data)
    _emit("session_updated", {"goal": data.get("active_goal", "") if isinstance(data, dict) else ""})

def save_project_history(data: dict):
    """حفظ project_history وتحديث Cache"""
    _write("project_history.json", data)
    _emit("project_history_updated", {"last_project": data.get("last_project", "") if isinstance(data, dict) else ""})

def update_roadmap_field(key: str, value):
    """تحديث حقل واحد في roadmap"""
    r = get_roadmap().copy()
    r[key] = value
    save_roadmap(r)

def update_session_field(key: str, value):
    """تحديث حقل واحد في session_state"""
    s = get_session_state().copy()
    s[key] = value
    save_session(s)
