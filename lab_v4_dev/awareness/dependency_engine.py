import os
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _get_index_dir():
    from lab_v4_dev.core.project_context import get_active_project_root, project_index_dir
    return project_index_dir(get_active_project_root())


def _load(name):
    path = os.path.join(_get_index_dir(), name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def index_missing() -> bool:
    """هل المشروع النشط حالياً بدون فهرس بُني له؟"""
    primary = os.path.join(_get_index_dir(), "project_snapshot.json")
    if os.path.exists(primary):
        return False
    # fallback: cache المحلي
    fallback = os.path.join(os.path.dirname(__file__), "..", "cache", "project_memory.json")
    fallback = os.path.normpath(fallback)
    return not os.path.exists(fallback)


def _path_to_module(file_path):
    # lab_v4_dev/core/agent.py -> lab_v4_dev.core.agent
    no_ext = file_path[:-3] if file_path.endswith(".py") else file_path
    return no_ext.replace(os.sep, ".").replace("/", ".")


def _module_to_path(module_name):
    return module_name.replace(".", os.sep) + ".py"


def what_imports(file_path):
    """ما الملفات/الوحدات التي يستوردها هذا الملف"""
    # أولاً: dependency_map.json (imports)
    dep_map = _load("dependency_map.json")
    if dep_map:
        if file_path in dep_map:
            return dep_map[file_path].get("imports", [])
        for key, data in dep_map.items():
            if key.endswith(file_path) or file_path.endswith(key):
                return data.get("imports", [])
    # ثانياً: dependency_graph.json كـ fallback
    graph = _load("dependency_graph.json")
    return graph.get("imports", {}).get(file_path, [])


def who_depends_on(file_path):
    """من يعتمد على هذا الملف - يقرأ من dependency_map أو dependency_graph"""
    result = set()

    # أولاً: dependency_map.json (imported_by)
    dep_map = _load("dependency_map.json")
    if dep_map:
        # مطابقة مباشرة
        if file_path in dep_map:
            result.update(dep_map[file_path].get("imported_by", []))
        # مطابقة جزئية
        for key, data in dep_map.items():
            if key.endswith(file_path) or file_path.endswith(key):
                result.update(data.get("imported_by", []))

    # ثانياً: dependency_graph.json (reverse_imports) كـ fallback
    graph = _load("dependency_graph.json")
    reverse = graph.get("reverse_imports", {})
    if file_path in reverse:
        result.update(reverse[file_path])
    module_name = _path_to_module(file_path)
    for key, deps in reverse.items():
        if key == module_name or key.endswith("." + module_name) or module_name.endswith("." + key):
            result.update(deps)


    # مطابقة جزئية: الملف بدون امتداد (TS قد يُستورد بدون .ts/.tsx)
    no_ext = file_path.rsplit(".", 1)[0] if "." in file_path.split("/")[-1] else file_path
    for key, deps in reverse.items():
        key_no_ext = key.rsplit(".", 1)[0] if "." in key.split("/")[-1] else key
        if key_no_ext == no_ext or key_no_ext.endswith("/" + no_ext.split("/")[-1]):
            result.update(deps)

    # استثناء ملفات stable/ و releases/
    EXCLUDE = ["stable/", "releases/", "workspace/", "project_indices/"]
    result = {r for r in result if not any(ex in r for ex in EXCLUDE)}
    return sorted(result)


def _load_memory():
    """تحميل project_memory للمشروع النشط"""
    try:
        from lab_v4_dev.core.project_context import (
            get_active_project_root,
            project_index_dir,
        )

        p = os.path.join(
            project_index_dir(get_active_project_root()),
            "project_memory.json",
        )

        with open(p, encoding="utf-8") as f:
            data = json.load(f)
            if data.get("total_files"):
                return data
    except Exception:
        pass
    try:
        fallback = os.path.join(os.path.dirname(__file__), "..", "cache", "project_memory.json")
        fallback = os.path.normpath(fallback)
        with open(fallback, encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}

def get_entry_points():
    snapshot = _load("project_snapshot.json")
    entries = snapshot.get("entry_points", [])
    if entries and entries != ["unknown"] and any(e != "unknown" for e in entries):
        return entries
    return _load_memory().get("entry_points", [])

def get_critical_files():
    snapshot = _load("project_snapshot.json")
    if snapshot.get("critical_files"):
        cf = snapshot["critical_files"]
    else:
        cf = _load_memory().get("critical_files", [])
    # نورجع strings فقط (project_memory يخزن dicts)
    result = []
    for item in cf:
        if isinstance(item, dict):
            result.append(item.get("file", ""))
        else:
            result.append(item)
    return [x for x in result if x]


def get_snapshot():
    return _load("project_snapshot.json")


if __name__ == "__main__":
    print("entry points:", get_entry_points())
    print("critical files:", get_critical_files())
    print("who depends on lab_v4_dev/memory/db.py:", who_depends_on("lab_v4_dev/memory/db.py"))


def get_impact_chain(file_path, max_depth=3):
    """تحليل تأثير تعديل ملف عبر BFS - مباشر وغير مباشر"""
    visited = {file_path}
    levels = {}
    current = [file_path]

    for depth in range(1, max_depth + 1):
        next_level = []
        for f in current:
            for dep in who_depends_on(f):
                if dep not in visited:
                    visited.add(dep)
                    next_level.append(dep)
        if not next_level:
            break
        levels[depth] = next_level
        current = next_level

    return {
        "file": file_path,
        "direct": levels.get(1, []),
        "indirect": [f for d in range(2, max_depth + 1) for f in levels.get(d, [])],
        "levels": levels,
        "total_affected": len(visited) - 1,
    }
