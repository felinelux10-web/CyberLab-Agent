# CyberLab Agent v4.7
# awareness/project_index.py

import os
import json
import ast

import os as _os
from lab_v4_dev.core.project_context import get_active_project_root, project_index_dir

def _index_file():
    return _os.path.join(project_index_dir(get_active_project_root()), "project_index.json")

# خريطة الملفات المعروفة
KNOWN_ROLES = {
    "core/orchestrator.py"    : "نقطة التحكم المركزية — يوجه كل الأوامر",
    "core/agent.py"           : "الوكيل الرئيسي — يبدأ النظام",
    "core/state.py"           : "حالة النظام (normal/safe/frozen)",
    "core/guard.py"           : "حارس الأوامر — يمنع الأوامر الخطرة",
    "llm/router.py"           : "قرار التوجيه — local أو Groq",
    "llm/groq_client.py"      : "اتصال Groq API",
    "intent/intent_parser.py" : "تحليل أوامر المستخدم",
    "intent/dictionary.py"    : "قاموس الأوامر العربية",
    "intent/intents.py"       : "تعريف كل الـ intents",
    "context/context_store.py": "حفظ السياق الحالي (version/file/subject)",
    "context/context_resolver.py": "ربط الأوامر بالسياق السابق",
    "awareness/release_analyzer.py": "تحليل تقارير الإصدارات",
    "awareness/project_memory.py"  : "ذاكرة المشروع (ملفات + تبعيات)",
    "memory/task_history.py"  : "سجل المهام المنفذة",
    "memory/session.py"       : "إحصائيات الجلسة الحالية",
    "monitor/self_diagnostics.py": "فحص صحة النظام",
    "monitor/health_check.py" : "فحص صحة الوكيل",
    "monitor/budget.py"       : "مراقبة موارد النظام",
    "data/work_tracker.py"    : "تتبع مهام التطوير (roadmap)",
    "executor/safe_pipeline.py": "تنفيذ آمن للأوامر",
    "loop/event_loop.py"      : "الحلقة الرئيسية للوكيل",
    "recovery/recovery.py"    : "استعادة النظام عند الأخطاء",
}

def build_index(base_dir: str = None) -> dict:
    if base_dir is None:
        base_dir = get_active_project_root()
    index = {}
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in ["__pycache__","cache","stable","releases","workspace"]]
        for fname in files:
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            full_path = os.path.join(root, fname)
            rel_path  = full_path.replace(base_dir + "/", "")
            functions = _extract_functions(full_path)
            role      = KNOWN_ROLES.get(rel_path, "")
            index[rel_path] = {
                "path"     : full_path,
                "layer"    : rel_path.split("/")[0] if "/" in rel_path else "root",
                "role"     : role,
                "functions": functions[:8],
            }
    return index

def _extract_functions(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        return [n.name for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    except:
        return []

def save_index(base_dir: str = None) -> str:
    if base_dir is None:
        from lab_v4_dev.core.project_context import get_active_project_root
        base_dir = get_active_project_root()
    index = build_index(base_dir)
    os.makedirs(os.path.dirname(_index_file()), exist_ok=True)
    with open(_index_file(), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return _index_file()

# ترجمة الاستعلامات العربية
ARABIC_SEARCH = {
    "توجيه"   : "router",
    "راوتر"   : "router",
    "روتر"    : "router",
    "سياق"    : "context",
    "ذاكرة"   : "memory",
    "تنفيذ"   : "executor",
    "مراقبة"  : "monitor",
    "خطة"     : "planner",
    "حلقة"    : "loop",
    "وكيل"    : "agent",
    "حارس"    : "guard",
    "اصدار"   : "release",
    "مهام"    : "task",
}

def search_index(query: str) -> list:
    try:
        with open(_index_file(), "r", encoding="utf-8") as f:
            index = json.load(f)
    except:
        index = build_index()

    # ترجم العربية إذا لزم
    query_en = ARABIC_SEARCH.get(query.strip(), query)
    query_lower = query_en.lower()
    results = []
    for path, info in index.items():
        score = 0
        if query_lower in path.lower():             score += 3
        if query_lower in info.get("role","").lower(): score += 2
        if any(query_lower in fn.lower() for fn in info.get("functions",[])): score += 1
        if score > 0:
            results.append({"path": path, "role": info.get("role",""), "score": score})

    return sorted(results, key=lambda x: x["score"], reverse=True)[:5]

def get_layer_map() -> dict:
    try:
        with open(_index_file(), "r", encoding="utf-8") as f:
            index = json.load(f)
    except:
        index = build_index()

    layers = {}
    for path, info in index.items():
        layer = info.get("layer", "?")
        layers.setdefault(layer, []).append(path)
    return layers
