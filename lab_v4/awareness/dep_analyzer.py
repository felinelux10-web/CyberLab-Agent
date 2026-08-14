# CyberLab Agent v4.6-prep
# awareness/dep_analyzer.py

import ast
import os
from lab_v4.memory.db import Database

def extract_imports(file_path: str) -> list:
    imports = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except Exception:
        pass
    return imports

def extract_functions(file_path: str) -> list:
    functions = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                functions.append(f"class:{node.name}")
    except Exception:
        pass
    return functions

def extract_calls(file_path: str) -> list:
    calls = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
    except Exception:
        pass
    return list(set(calls))

def analyze_file(file_path: str) -> dict:
    imports   = extract_imports(file_path)
    functions = extract_functions(file_path)
    calls     = extract_calls(file_path)

    # حدد الملفات المحلية فقط
    local_imports = [
        i for i in imports
        if i.startswith("lab_v4") or i.startswith("stable")
    ]

    return {
        "path"         : file_path,
        "imports"      : imports,
        "local_imports": local_imports,
        "functions"    : functions,
        "calls"        : calls,
        "risk"         : _estimate_risk(local_imports, functions),
    }

def _estimate_risk(imports: list, functions: list) -> str:
    if len(imports) > 5 or len(functions) > 10:
        return "high"
    elif len(imports) > 2 or len(functions) > 5:
        return "medium"
    return "low"

def build_dependency_graph(directory: str, db: Database) -> dict:
    graph = {}
    py_files = []

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ["__pycache__", "archives", "cache"]]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    for file_path in py_files:
        analysis = analyze_file(file_path)
        graph[file_path] = analysis

        # احفظ في DB
        db.execute(
            """INSERT OR REPLACE INTO project_map
               (file_path, file_hash, summary, last_scanned)
               VALUES (?, ?, ?, datetime('now'))""",
            (
                file_path,
                str(hash(str(analysis))),
                f"functions:{len(analysis['functions'])} imports:{len(analysis['imports'])} risk:{analysis['risk']}",
            )
        )

    return graph

def detect_circular(graph: dict) -> list:
    circular = []
    for file, data in graph.items():
        for imp in data["local_imports"]:
            imp_path = imp.replace(".", "/") + ".py"
            for other_file, other_data in graph.items():
                if imp_path in other_file:
                    for other_imp in other_data["local_imports"]:
                        if file.replace("/", ".").replace(".py", "") in other_imp:
                            circular.append((file, other_file))
    return circular
