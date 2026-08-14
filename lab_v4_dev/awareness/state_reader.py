# CyberLab Agent v4.6
# awareness/state_reader.py
#
# ARCHITECTURAL NOTE:
# StateReader owns only runtime/session state.
# Project metadata must come from ProjectMetadata.
# Project structure must come from ProjectMemory / ProjectIndex.
# Do not use StateReader as Source of Truth for project metadata.

import json, os
from datetime import datetime
from lab_v4_dev.core.project_context import (
    get_active_project_root,
    project_index_dir,
)

def _state_file():
    return os.path.join(
        project_index_dir(get_active_project_root()),
        "project_state.json"
    )


def load() -> dict:
    try:
        with open(_state_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get(key: str, default=None):
    return load().get(key, default)

def update(key: str, value):
    state = load()
    state[key] = value
    state["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(_state_file()), exist_ok=True)
    with open(_state_file(), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def add_modified_file(file_path: str):
    state = load()
    files = state.get("last_modified_files", [])
    if file_path not in files:
        files.insert(0, file_path)
    state["last_modified_files"] = files[:10]
    state["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(_state_file()), exist_ok=True)
    with open(_state_file(), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def summary() -> str:
    s = load()
    # A: من ProjectMetadata
    try:
        from lab_v4_dev.core.project_metadata import ProjectMetadata
        _meta = ProjectMetadata()
        _name    = _meta.get_project_name()
        _version = _meta.get_version()
        _phases  = 1 if _meta.get_current_phase() else 0
    except Exception:
        _name, _version, _phases = "CyberLab Agent", "?", 0
    # B: من project_memory (عبر Memory Router الموحد)
    try:
        from lab_v4_dev.memory.router import get_project_memory
        _mem = get_project_memory()
        _files = _mem.get("total_files", 0)
    except Exception:
        _files = 0
    # C: من state_reader (مملوك هنا)
    _updated = s.get("last_updated", "?")[:10]
    return (
        f"المشروع: {_name} v{_version} | "
        f"ملفات: {_files} | "
        f"مراحل مكتملة: {_phases} | "
        f"آخر تحديث: {_updated}"
    )
