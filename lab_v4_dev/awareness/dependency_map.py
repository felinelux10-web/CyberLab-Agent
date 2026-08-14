# CyberLab Agent v4.7
# awareness/dependency_map.py

import ast
import os
import json

def _map_file():
    from lab_v4_dev.core.project_context import get_active_project_root, project_index_dir
    import os
    return os.path.join(project_index_dir(get_active_project_root()), "dependency_map.json")

def extract_local_imports(file_path: str, base_dir: str) -> list:
    """يستخرج الاستيرادات المحلية — يبحث في كل المجلدات الفرعية"""
    imports = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.replace(".", "/") + ".py"
                found = False
                # بحث في كل المجلدات الفرعية
                for root, dirs, files in os.walk(base_dir):
                    dirs[:] = [d for d in dirs if d not in ["__pycache__",".git","node_modules"]]
                    candidate = os.path.join(root, parts)
                    if os.path.exists(candidate):
                        rel = os.path.relpath(candidate, base_dir)
                        imports.append(rel)
                        found = True
                        break
                    # جرب الجزء الأخير فقط
                    last = node.module.split(".")[-1] + ".py"
                    candidate2 = os.path.join(root, last)
                    if os.path.exists(candidate2) and not found:
                        rel = os.path.relpath(candidate2, base_dir)
                        imports.append(rel)
                        found = True
                        break
    except:
        pass
    return list(set(imports))

def build_dependency_map(base_dir: str = None) -> dict:
    if base_dir is None:
        from lab_v4_dev.core.project_context import get_active_project_root
        base_dir = get_active_project_root()
    dep_map = {}
    all_files = []

    # تحديد مجلد المصدر الفعلي فقط
    src_dirs = ["lab_v4_dev"] if os.path.basename(base_dir) == "cyberlab_agent" else ["."]
    for src in src_dirs:
        src_path = os.path.join(base_dir, src) if src != "." else base_dir
        if not os.path.exists(src_path):
            src_path = base_dir
        for root, dirs, files in os.walk(src_path):
            dirs[:] = [d for d in dirs if d not in ["__pycache__","cache","stable","releases","project_indices"]]
            for f in files:
                if f.endswith(".py") and f != "__init__.py":
                    all_files.append(os.path.join(root, f))

    for file_path in all_files:
        rel = file_path.replace(base_dir + "/", "")
        imports = extract_local_imports(file_path, base_dir)
        dep_map[rel] = {
            "imports"  : imports,
            "imported_by": [],
        }

    # نحسب من يستورد من؟
    for file_path, data in dep_map.items():
        for imp in data["imports"]:
            # نبحث بالاسم الجزئي بدل المطابقة الكاملة
            for key in dep_map:
                if key.endswith(imp) or imp.endswith(key):
                    dep_map[key]["imported_by"].append(file_path)
                    break

    return dep_map

def save_map(base_dir: str = None) -> str:
    if base_dir is None:
        from lab_v4_dev.core.project_context import get_active_project_root
        base_dir = get_active_project_root()
    dep_map = build_dependency_map(base_dir)
    os.makedirs(os.path.dirname(_map_file()), exist_ok=True)
    with open(_map_file(), "w", encoding="utf-8") as f:
        json.dump(dep_map, f, ensure_ascii=False, indent=2)
    return _map_file()

def get_critical_files() -> list:
    """الملفات التي يعتمد عليها الكثيرون = حرجة"""
    try:
        with open(_map_file(), "r", encoding="utf-8") as f:
            dep_map = json.load(f)
    except:
        dep_map = build_dependency_map()

    critical = []
    for path, data in dep_map.items():
        count = len(data.get("imported_by", []))
        if count >= 2:
            critical.append({"file": path, "used_by": count})

    return sorted(critical, key=lambda x: x["used_by"], reverse=True)

def get_impact(file_path: str) -> dict:
    """ما تأثير تعديل هذا الملف؟"""
    try:
        with open(_map_file(), "r", encoding="utf-8") as f:
            dep_map = json.load(f)
    except:
        dep_map = build_dependency_map()

    # نبحث بالاسم الجزئي
    matches = [k for k in dep_map if file_path in k]
    if not matches:
        return {"file": file_path, "impact": [], "risk": "unknown"}

    key  = matches[0]
    data = dep_map[key]
    imported_by = data.get("imported_by", [])

    risk = "high" if len(imported_by) >= 3 else \
           "medium" if len(imported_by) >= 1 else "low"

    return {
        "file"       : key,
        "imports"    : data.get("imports", []),
        "imported_by": imported_by,
        "risk"       : risk,
    }

def get_orphans() -> list:
    """الملفات التي لا يستوردها أحد"""
    try:
        with open(_map_file(), "r", encoding="utf-8") as f:
            dep_map = json.load(f)
    except:
        dep_map = build_dependency_map()

    return [
        path for path, data in dep_map.items()
        if not data.get("imported_by") and not data.get("imports")
    ]
