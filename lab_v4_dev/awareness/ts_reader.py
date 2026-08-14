"""
TS/JS Project Reader - v5.9
يقرأ مشاريع TypeScript/JavaScript ويبني فهرس مشابه لـ project_reader.py
"""
import os
import re
import json
from collections import defaultdict
from datetime import datetime


def scan_project(project_root: str) -> dict:
    project_root = os.path.abspath(project_root)
    files = []
    imports = defaultdict(set)
    reverse_imports = defaultdict(set)

    SKIP = {"node_modules", ".git", ".manus", "dist", "build", "__pycache__", "stable", "releases"}
    EXTS = {".ts", ".tsx", ".js", ".jsx"}

    for root, dirs, filenames in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in filenames:
            if any(f.endswith(e) for e in EXTS):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, project_root)
                files.append(rel)

    # استخراج alias mapping من tsconfig.json
    alias_map = {}
    for cfg in ["tsconfig.json", "tsconfig.app.json"]:
        cfg_path = os.path.join(project_root, cfg)
        if os.path.exists(cfg_path):
            try:
                cfg_data = json.load(open(cfg_path, encoding="utf-8"))
                paths = cfg_data.get("compilerOptions", {}).get("paths", {})
                base = cfg_data.get("compilerOptions", {}).get("baseUrl", ".")
                for alias, targets in paths.items():
                    prefix = alias.rstrip("/*")
                    if targets:
                        target = targets[0].rstrip("/*")
                        alias_map[prefix] = os.path.normpath(
                            os.path.join(project_root, base, target))
            except Exception:
                pass
        if alias_map:
            break

    def resolve_import(imp: str, source_file: str) -> str:
        """يحول import إلى مسار نسبي للمشروع"""
        # مسار نسبي عادي
        if imp.startswith("."):
            src_dir = os.path.dirname(os.path.join(project_root, source_file))
            resolved = os.path.normpath(os.path.join(src_dir, imp))
            # إضافة امتداد إن لزم
            for ext in [".ts", ".tsx", ".js", ".jsx"]:
                if os.path.exists(resolved + ext):
                    return os.path.relpath(resolved + ext, project_root)
            return os.path.relpath(resolved, project_root)
        # alias
        for prefix, target_dir in alias_map.items():
            if imp == prefix or imp.startswith(prefix + "/"):
                rest = imp[len(prefix):].lstrip("/")
                resolved = os.path.join(target_dir, rest)
                for ext in [".ts", ".tsx", ".js", ".jsx"]:
                    if os.path.exists(resolved + ext):
                        return os.path.relpath(resolved + ext, project_root)
                return os.path.relpath(resolved, project_root)
        return ""

    for f in files:
        full = os.path.join(project_root, f)
        try:
            content = open(full, encoding="utf-8", errors="ignore").read()
            found = re.findall(
                r'''(?:import|from)\s+['"]([^'"]+)['"]''', content
            )
            for imp in found:
                resolved = resolve_import(imp, f)
                if resolved:
                    imports[f].add(resolved)
                    reverse_imports[resolved].add(f)
        except Exception:
            pass

    # entry points
    entry_candidates = ["client/src/main.tsx","client/src/App.tsx",
                        "server/index.ts","src/main.tsx","src/index.tsx",
                        "index.ts","index.js"]
    entries = [e for e in entry_candidates
               if os.path.exists(os.path.join(project_root, e))]

    # critical files
    internal = {k: list(v) for k, v in reverse_imports.items()}
    critical = sorted(internal.keys(),
                      key=lambda x: len(internal[x]),
                      reverse=True)[:10]

    snapshot = {
        "generated_at": datetime.now().isoformat(),
        "project_root": project_root,
        "project_type": "typescript",
        "total_files": len(files),
        "entry_points": entries,
        "critical_files": critical,
        "modules_count": len(imports),
    }

    index = {
        "generated_at": datetime.now().isoformat(),
        "project_root": project_root,
        "total_files": len(files),
        "files": files,
    }

    graph = {
        "imports": {k: list(v) for k, v in imports.items()},
        "reverse_imports": {k: list(v) for k, v in reverse_imports.items()},
    }

    # حفظ في workspace
    out_dir = os.path.expanduser(
        "~/cyberlab_agent/workspace/external_index")
    os.makedirs(out_dir, exist_ok=True)

    def w(name, data):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    w("project_index.json", index)
    w("dependency_graph.json", graph)
    w("project_snapshot.json", snapshot)

    return snapshot


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.expanduser("~/external_projects/dynamic-lab-app")
    result = scan_project(path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
