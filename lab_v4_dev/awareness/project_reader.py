import os
import ast
import json
from collections import defaultdict
from datetime import datetime


def _get_project_root():
    from lab_v4_dev.core.project_context import get_active_project_root
    return get_active_project_root()


def _get_output_dir():
    from lab_v4_dev.core.project_context import get_active_project_root, project_index_dir
    return project_index_dir(get_active_project_root())


def _find_entry_points(base_dir: str) -> list:
    candidates = ["main.py", "run.py", "app.py", "server.py", "cli.py", "__main__.py"]
    found = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "tests", "test", "stable", "releases"]]
        for f in files:
            if f in candidates:
                rel = os.path.relpath(os.path.join(root, f), base_dir)
                found.append(rel)
    return found or ["unknown"]


class ProjectReader:
    def __init__(self):
        self.files = []
        self.imports = defaultdict(set)
        self.reverse_imports = defaultdict(set)

    def scan_files(self):
        base = _get_project_root()
        for root, dirs, files in os.walk(base):
            if ".git" in root or "__pycache__" in root:
                continue
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, base)
                    self.files.append(rel_path)
        return self.files

    def parse_file(self, file_path):
        base = _get_project_root()
        full_path = os.path.join(base, file_path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        self.imports[file_path].add(n.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.imports[file_path].add(node.module)
        except Exception:
            pass

    def build_graph(self):
        for f in self.files:
            self.parse_file(f)
        for src, deps in self.imports.items():
            for d in deps:
                self.reverse_imports[d].add(src)

    def generate_outputs(self):
        base = _get_project_root()
        out = _get_output_dir()
        os.makedirs(out, exist_ok=True)

        index = {
            "generated_at": datetime.now().isoformat(),
            "total_files": len(self.files),
            "files": self.files,
        }
        graph = {
            "imports": {k: list(v) for k, v in self.imports.items()},
            "reverse_imports": {k: list(v) for k, v in self.reverse_imports.items()},
        }
        # نستخدم ملفات المشروع الفعلية من project_index
        project_files = set(self.files)
        # نحسب الملفات الأكثر استخداماً من reverse_imports
        # لكن نطابق فقط مع ملفات المشروع الفعلية
        file_scores = {}
        for mod, importers in self.reverse_imports.items():
            # نبحث عن ملف يطابق هذا الـ module
            mod_path = mod.replace(".", "/") + ".py"
            for f in project_files:
                if f.endswith(mod_path) or f == mod_path:
                    file_scores[f] = len(importers)
                    break
        # إذا لم نجد تطابق، نأخذ الملفات الأكثر استيراداً من project_index
        if not file_scores:
            file_scores = {f: 1 for f in project_files if not f.endswith("__init__.py")}
        critical = sorted(file_scores, key=lambda x: file_scores[x], reverse=True)[:10]
        snapshot = {
            "generated_at": datetime.now().isoformat(),
            "entry_points": _find_entry_points(base),
            "critical_files": critical,
            "modules_count": len(self.imports),
            "total_files": len(self.files),
        }
        self.write_json("project_index.json", index)
        self.write_json("dependency_graph.json", graph)
        self.write_json("critical_files.json", {"critical": critical})
        self.write_json("project_snapshot.json", snapshot)

    def write_json(self, name, data):
        path = os.path.join(_get_output_dir(), name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def run(self):
        self.scan_files()
        self.build_graph()
        self.generate_outputs()
        return True


def build_project_index():
    reader = ProjectReader()
    reader.run()
    return reader
