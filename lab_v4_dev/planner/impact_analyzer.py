# CyberLab Agent v4.6-prep
# planner/impact_analyzer.py

import json
from lab_v4_dev.awareness.project_memory import load_memory

RISK_SCORES = {"high": 3, "medium": 2, "low": 1}

def analyze_impact(file_path: str) -> dict:
    memory = load_memory()
    deps   = memory.get("dependencies", {})
    short  = file_path.replace("lab_v4_dev/", "")

    # من يعتمد على هذا الملف؟
    affected = []
    for f, f_deps in deps.items():
        for d in f_deps:
            if short.replace("/", ".").replace(".py", "") in d:
                affected.append(f)

    # هل الملف حرج؟
    is_critical = any(
        c["file"] == file_path
        for c in memory.get("critical_files", [])
    )

    # حساب درجة الخطر
    risk_score = len(affected) * 2
    if is_critical:
        risk_score += 5

    if risk_score >= 8:
        risk_level = "high"
    elif risk_score >= 4:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "file"        : file_path,
        "affected"    : affected,
        "affected_count": len(affected),
        "is_critical" : is_critical,
        "risk_score"  : risk_score,
        "risk_level"  : risk_level,
        "recommendation": _recommend(risk_level, affected),
    }

def _recommend(risk_level: str, affected: list) -> str:
    if risk_level == "high":
        return "تحذير: تعديل خطير — خذ snapshot كامل أولاً"
    elif risk_level == "medium":
        return "تنبيه: تعديل متوسط الخطر — تحقق من الملفات المتأثرة"
    return "آمن: تعديل منخفض الخطر"
