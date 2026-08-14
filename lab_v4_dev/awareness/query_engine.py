"""
Query Engine - v5.2.2
نقطة استعلام موحدة عن المشروع، تبني على dependency_engine.
تُرجع نتائج بصيغة dict موحدة (Schema) قابلة لإعادة الاستخدام
من قبل intents الحالية أو Modification Planner لاحقاً.
"""

from lab_v4_dev.awareness import dependency_engine as de


def _path_to_module(file_path):
    no_ext = file_path[:-3] if file_path.endswith(".py") else file_path
    return no_ext.replace("/", ".").replace("\\", ".")


def risk_level(score):
    """تصنيف نصي لدرجة الخطورة"""
    if score >= 70:
        return "critical"
    if score >= 40:
        return "high"
    if score >= 15:
        return "medium"
    return "low"


def _risk_score(file_path, chain=None):
    """حساب درجة الخطورة: تأثير مباشر + غير مباشر + entry point + critical file"""
    if chain is None:
        chain = de.get_impact_chain(file_path)

    direct = len(chain["direct"])
    indirect = len(chain["indirect"])
    is_entry = file_path in de.get_entry_points()

    module_name = _path_to_module(file_path)
    critical_files = de.get_critical_files()
    is_critical = any(module_name in cf or cf.endswith("." + module_name) for cf in critical_files)

    score = direct * 8 + indirect * 2
    if is_entry:
        score += 20
    if is_critical:
        score += 15

    return min(score, 100)


def query_file(file_path):
    """الاستعلام الموحد عن ملف: اعتماديات + تأثير + خطورة"""
    chain = de.get_impact_chain(file_path)
    score = _risk_score(file_path, chain)
    return {
        "file": file_path,
        "direct_dependencies": chain["direct"],
        "indirect_dependencies": chain["indirect"],
        "total_affected": chain["total_affected"],
        "risk_score": score,
        "risk_level": risk_level(score),
        "is_entry_point": file_path in de.get_entry_points(),
    }


def query_project_overview():
    """نظرة عامة موحدة على المشروع"""
    snapshot = de.get_snapshot()
    return {
        "entry_points": snapshot.get("entry_points", []),
        "critical_files": snapshot.get("critical_files", []),
        "total_files": snapshot.get("total_files", 0),
        "modules_count": snapshot.get("modules_count", 0),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(query_file("memory/db.py"), indent=2, ensure_ascii=False))
    print(json.dumps(query_project_overview(), indent=2, ensure_ascii=False))
