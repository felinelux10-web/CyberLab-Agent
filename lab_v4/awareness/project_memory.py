# CyberLab Agent v4.6-prep
# awareness/project_memory.py

import json
import os
from datetime import datetime
from lab_v4.awareness.dep_analyzer import build_dependency_graph, analyze_file

MEMORY_FILE = "lab_v4/cache/project_memory.json"

def build_memory(db) -> dict:
    graph = build_dependency_graph("lab_v4", db)

    memory = {
        "version"      : "4.6-prep",
        "last_updated" : datetime.now().isoformat(),
        "total_files"  : len(graph),
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
            if f"lab_v4/{layer}/" in f:
                layers[layer].append(f.replace("lab_v4/", ""))

    memory["architecture"] = layers

    # التبعيات
    for f, d in graph.items():
        if d["local_imports"]:
            short = f.replace("lab_v4/", "")
            memory["dependencies"][short] = d["local_imports"]

    return memory

def save_memory(db) -> str:
    memory = build_memory(db)
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    return MEMORY_FILE

def load_memory() -> dict:
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_file_info(file_path: str) -> dict:
    memory = load_memory()
    deps = memory.get("dependencies", {})
    short = file_path.replace("lab_v4/", "")
    return {
        "file"        : file_path,
        "dependencies": deps.get(short, []),
        "is_critical" : any(
            c["file"] == file_path
            for c in memory.get("critical_files", [])
        ),
    }
