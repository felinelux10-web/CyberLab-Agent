# CyberLab Agent v4.6-prep
# awareness/project_memory.py

import json
import os
from datetime import datetime
from lab_v4_dev.awareness.dep_analyzer import build_dependency_graph, analyze_file
from lab_v4_dev.core.project_context import get_active_project_root, project_index_dir

def _memory_file():
    root = get_active_project_root()
    return os.path.join(project_index_dir(root), "project_memory.json")


def build_memory(db) -> dict:
    graph = build_dependency_graph(get_active_project_root(), db)

    memory = {
        "version"      : "derived",
        "last_updated" : datetime.now().isoformat(),
        "total_files"  : len(graph),
        "entry_points" : ["lab_v4_dev/run.py"],
        "entrypoint"   : "run.py",
        "critical_files": [],
        "architecture" : {},
        "dependencies" : {},
    }

    # الملفات الحرجة
    for f, d in graph.items():
        if d["risk"] == "high":
            memory["critical_files"].append({
                "file"     : f,
                "functions": d["functions"][:5],
                "risk"     : d["risk"],
            })

    # بنية المعمارية
    layers = {
        "core"     : [],
        "loop"     : [],
        "intent"   : [],
        "planner"  : [],
        "executor" : [],
        "memory"   : [],
        "awareness": [],
        "recovery" : [],
        "monitor"  : [],
        "cli"      : [],
    }

    for f in graph.keys():
        for layer in layers:
            parts = f.replace("\\","/").split("/")
            if layer in parts:
                idx = parts.index(layer)
                layers[layer].append("/".join(parts[idx:]))

    memory["architecture"] = layers

    # التبعيات
    for f, d in graph.items():
        if d["local_imports"]:
            short = f.replace("\\","/").split("/",1)[1] if "/" in f.replace("\\","/") else f
            memory["dependencies"][short] = d["local_imports"]

    return memory

def save_memory(db) -> str:
    memory = build_memory(db)
    os.makedirs(os.path.dirname(_memory_file()), exist_ok=True)
    with open(_memory_file(), "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    return _memory_file()

def load_memory() -> dict:
    # أولاً: مسار الفهرس الديناميكي
    primary = _memory_file()
    # ثانياً: fallback للـ cache المحلي
    fallback = os.path.join(os.path.dirname(__file__), "..", "cache", "project_memory.json")
    fallback = os.path.normpath(fallback)
    for p in [primary, fallback]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("total_files"):
                    return data
        except Exception:
            pass
    return {}

def get_file_info(file_path: str) -> dict:
    memory = load_memory()
    deps = memory.get("dependencies", {})
    short = file_path.replace("\\","/").split("/",1)[1] if "/" in file_path.replace("\\","/") else file_path
    return {
        "file"        : file_path,
        "dependencies": deps.get(short, []),
        "is_critical" : any(
            c["file"] == file_path
            for c in memory.get("critical_files", [])
        ),
    }
