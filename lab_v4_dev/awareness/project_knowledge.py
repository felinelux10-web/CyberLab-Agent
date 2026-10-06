# CyberLab Agent v5.9.8.B
# awareness/project_knowledge.py
# Single Source of Truth for project knowledge and project state

from __future__ import annotations

import ast
import json
import os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BASE = os.path.expanduser("~/cyberlab_agent")
DATA = os.path.join(BASE, "project_data")

# ─── Cache Layer ───
_cache = {}
_cache_state = {
    "loaded": False,
    "dirty": False,
    "loaded_at": None,
    "last_refresh": None,
    "last_write": None,
    "version": 0,
}

# ─── Event Log ───
_events = []
_MAX_EVENTS = 100


def _emit(event: str, payload: dict = None):
    """تسجيل حدث داخلي"""
    global _events
    _events.append({
        "event": event,
        "time": _time.time(),
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


# ---------------------------------------------------------------------------
# Canonical Project Knowledge Model
# ---------------------------------------------------------------------------

class ConfidenceLevel:
    """Levels used to qualify knowledge claims."""
    STATIC_VERIFIED = "static_verified"
    RUNTIME_VERIFIED = "runtime_verified"
    TEST_VERIFIED = "test_verified"
    INFERRED = "inferred"
    HISTORICAL = "historical"


@dataclass
class Provenance:
    source: str
    evidence: str
    confidence: str = ConfidenceLevel.STATIC_VERIFIED
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    verified_by: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "discovered_at": self.discovered_at,
            "verified_by": self.verified_by,
        }


@dataclass
class ProjectKnowledgeRelationship:
    type: str
    from_entity: str
    to_entity: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Optional[Provenance] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "metadata": self.metadata,
            "provenance": self.provenance.as_dict() if self.provenance else None,
        }


@dataclass
class ProjectKnowledgeEntity:
    id: str
    name: str
    type: str
    path: str
    layer: Optional[str] = None
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Optional[Provenance] = None
    relationships: List[ProjectKnowledgeRelationship] = field(default_factory=list)

    def add_relationship(self, relationship: ProjectKnowledgeRelationship):
        self.relationships.append(relationship)

    def add_child(self, child_id: str):
        if child_id not in self.children:
            self.children.append(child_id)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "layer": self.layer,
            "parent": self.parent,
            "children": self.children,
            "metadata": self.metadata,
            "provenance": self.provenance.as_dict() if self.provenance else None,
            "relationships": [r.as_dict() for r in self.relationships],
        }


@dataclass
class ProjectKnowledgeModel:
    repository_path: str
    project_name: str = "CyberLab Agent"
    version: str = "current"
    last_scanned: str = field(default_factory=lambda: datetime.now().isoformat())
    entities: Dict[str, ProjectKnowledgeEntity] = field(default_factory=dict)
    relationships: List[ProjectKnowledgeRelationship] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    layers: Dict[str, str] = field(default_factory=dict)

    def add_entity(self, entity: ProjectKnowledgeEntity):
        self.entities[entity.id] = entity
        if entity.layer:
            self.layers.setdefault(entity.layer, entity.layer)

    def add_relationship(self, relationship: ProjectKnowledgeRelationship):
        self.relationships.append(relationship)
        if relationship.from_entity in self.entities:
            self.entities[relationship.from_entity].add_relationship(relationship)

    def get_entity_by_path(self, path: str) -> Optional[ProjectKnowledgeEntity]:
        for entity in self.entities.values():
            if entity.path == path:
                return entity
        return None

    def get_related_entities(self, entity_id: str) -> List[ProjectKnowledgeEntity]:
        found: set[str] = set()
        for rel in self.relationships:
            if rel.from_entity == entity_id:
                found.add(rel.to_entity)
            if rel.to_entity == entity_id:
                found.add(rel.from_entity)
        return [self.entities[eid] for eid in sorted(found) if eid in self.entities]

    def to_snapshot(self) -> Dict[str, Any]:
        return {
            "repository": self.repository_path,
            "project_name": self.project_name,
            "version": self.version,
            "last_scanned": self.last_scanned,
            "files": [entity.path for entity in sorted(self.entities.values(), key=lambda x: x.path)],
            "layers": list(sorted(self.layers.keys())),
            "entry_points": self.entry_points,
            "relationships_count": len(self.relationships),
            "entities_count": len(self.entities),
        }


def _project_root_from_context() -> str:
    """Find the active project root from common local paths."""
    candidates = [
        os.getcwd(),
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        os.path.join(os.path.expanduser("~"), "cyberlab_agent"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            if os.path.exists(os.path.join(candidate, "lab_v4_dev")):
                return candidate
    return os.getcwd()


def _summarize_ast(file_path: str) -> Dict[str, Any]:
    """Collect simplest static facts from a Python file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
            source = handle.read()
        tree = ast.parse(source)
    except Exception:
        return {"functions": [], "classes": [], "imports": [], "calls": []}

    functions: List[str] = []
    classes: List[str] = []
    imports: List[str] = []
    calls: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    return {
        "functions": sorted(set(functions)),
        "classes": sorted(set(classes)),
        "imports": sorted(set(imports)),
        "calls": sorted(set(calls)),
    }


def _infer_layer(rel_path: str) -> str:
    parts = rel_path.replace("\\", "/").split("/")
    if not parts:
        return "root"
    if len(parts) == 1:
        return "repository"
    if parts[0] == "tests":
        return "tests"
    if parts[0] == "lab_v4_dev":
        return f"lab_v4_dev/{parts[1]}"
    return "repository"


def build_project_knowledge(root: Optional[str] = None) -> ProjectKnowledgeModel:
    """Build a canonical live project knowledge model from source files."""
    project_root = root or _project_root_from_context()
    project_name = os.path.basename(project_root) or "CyberLab Agent"
    model = ProjectKnowledgeModel(
        repository_path=project_root,
        project_name=project_name,
        version="current",
    )

    excluded_dirs = {
        "__pycache__",
        "cache",
        "stable",
        "releases",
        "workspace",
        "archive",
        "archives",
        "lab_v4",
        "legacy",
        "_archived_orphans_20260621",
        "project_indices",
        ".git",
    }

    for current_root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        for filename in files:
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
            full_path = os.path.join(current_root, filename)
            rel_path = os.path.relpath(full_path, project_root).replace("\\", "/")
            layer = _infer_layer(rel_path)
            entity_id = rel_path
            entity = ProjectKnowledgeEntity(
                id=entity_id,
                name=os.path.splitext(filename)[0],
                type="file",
                path=rel_path,
                layer=layer,
                metadata={
                    "size": os.path.getsize(full_path),
                },
                provenance=Provenance(
                    source=rel_path,
                    evidence="static file scan",
                    confidence=ConfidenceLevel.STATIC_VERIFIED,
                ),
            )

            summary = _summarize_ast(full_path)
            entity.metadata.update({
                "functions": summary["functions"],
                "classes": summary["classes"],
                "imports": summary["imports"],
                "calls": summary["calls"],
            })
            model.add_entity(entity)

            # Create relationship edges for imports and calls.
            for imported in summary["imports"]:
                target = imported.replace(".", "/") + ".py"
                if target.startswith("lab_v4_dev/"):
                    target_id = target
                    model.add_relationship(
                        ProjectKnowledgeRelationship(
                            type="import",
                            from_entity=entity_id,
                            to_entity=target_id,
                            metadata={"import_name": imported},
                            provenance=Provenance(
                                source=rel_path,
                                evidence="import statement",
                                confidence=ConfidenceLevel.STATIC_VERIFIED,
                            ),
                        )
                    )

            for call_name in summary["calls"]:
                model.add_relationship(
                    ProjectKnowledgeRelationship(
                        type="call",
                        from_entity=entity_id,
                        to_entity=call_name,
                        metadata={"call_name": call_name},
                        provenance=Provenance(
                            source=rel_path,
                            evidence="call expression",
                            confidence=ConfidenceLevel.STATIC_VERIFIED,
                        ),
                    )
                )

    # Add entry points heuristically.
    preferred = [
        "run.py",
        "lab_v4_dev/core/agent.py",
        "lab_v4_dev/conversation/conversation_manager.py",
        "lab_v4_dev/core/orchestrator.py",
    ]
    for candidate in preferred:
        if model.get_entity_by_path(candidate):
            model.entry_points.append(candidate)

    return model


def get_project_knowledge_snapshot(root: Optional[str] = None) -> Dict[str, Any]:
    """Return a compact live snapshot for prompt builder and self-knowledge lookups."""
    model = build_project_knowledge(root=root)
    return model.to_snapshot()


def query_project_knowledge(query: str, root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Basic free-text retrieval over path and metadata names."""
    model = build_project_knowledge(root=root)
    q = str(query or "").strip().lower()
    if not q:
        return []

    results: List[Dict[str, Any]] = []
    for entity in model.entities.values():
        hay = " ".join([
            entity.path,
            entity.name,
            entity.layer or "",
            *entity.metadata.get("functions", []),
            *entity.metadata.get("classes", []),
        ]).lower()
        score = 0
        if q in hay:
            score += 3
        if q in entity.path.lower():
            score += 2
        if q in entity.name.lower():
            score += 2
        if score:
            results.append({
                "path": entity.path,
                "name": entity.name,
                "layer": entity.layer,
                "score": score,
                "role": entity.metadata.get("classes", [])[:1],
            })

    return sorted(results, key=lambda item: item["score"], reverse=True)[:10]


def get_build_status() -> Dict[str, Any]:
    """Expose the current project knowledge load state in a compact form."""
    snapshot = get_project_knowledge_snapshot()
    return {
        "ready": bool(snapshot.get("files")),
        "total_files": len(snapshot.get("files", [])),
        "layers": snapshot.get("layers", []),
        "project_name": snapshot.get("project_name"),
    }


def _load_all():
    """تحميل جميع الملفات مرة واحدة عند أول استدعاء"""
    global _cache, _cache_state
    if _cache_state["loaded"]:
        return
    for filename in ["roadmap.json", "session_state.json", "project_history.json", "version_history.json"]:
        fpath = os.path.join(DATA, filename)
        if os.path.exists(fpath):
            try:
                with open(fpath, encoding="utf-8") as f:
                    _cache[filename] = json.load(f)
            except Exception:
                _cache[filename] = {}
        else:
            _cache[filename] = {}
    _cache_state["loaded"] = True
    _cache_state["dirty"] = False
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
    _cache_state["dirty"] = False


def reload_file(filename: str):
    """إعادة تحميل ملف واحد فقط من القرص"""
    global _cache
    _load_all()
    fpath = os.path.join(DATA, filename)
    if os.path.exists(fpath):
        try:
            with open(fpath, encoding="utf-8") as f:
                _cache[filename] = json.load(f)
        except Exception:
            _cache[filename] = {}
    else:
        _cache[filename] = {}


def invalidate_cache():
    """إبطال الـ Cache وإجبار إعادة التحميل عند الطلب التالي"""
    global _cache, _cache_state
    _cache = {}
    _cache_state["loaded"] = False
    _cache_state["dirty"] = False


def cache_status() -> dict:
    """معلومات كاملة عن حالة Cache"""
    return {
        "loaded": _cache_state["loaded"],
        "dirty": _cache_state["dirty"],
        "loaded_at": _cache_state["loaded_at"],
        "last_refresh": _cache_state["last_refresh"],
        "last_write": _cache_state["last_write"],
        "version": _cache_state["version"],
        "files": list(_cache.keys()),
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
        from lab_v4_dev.core.project_metadata import ProjectMetadata
        return ProjectMetadata().get_version()
    except Exception:
        return "?"


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
        "version": version,
        "current_focus": roadmap.get("current_focus", "?"),
        "active": roadmap.get("active", []),
        "planned": roadmap.get("planned", []),
        "completed_count": len(roadmap.get("completed", [])),
        "last_project": history.get("last_project", "?"),
        "last_goal": session.get("active_goal", "?"),
        "last_step": session.get("next_step", "?"),
        "last_files": session.get("last_files", []),
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
    _cache[filename] = data
    _cache_state["last_write"] = _time.time()
    _cache_state["dirty"] = False
    _cache_state["version"] += 1


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
