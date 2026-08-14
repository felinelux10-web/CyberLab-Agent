"""
v5.3.1 — Trust & Risk Labeling
تصنيف كل intent بمستوى الثقة/الخطورة
"""
from lab_v4_dev.intent.intents import Intent

# read_only: قراءة فقط، آمنة 100%
# safe_write: كتابة محمية بـ safe_write (backup+audit)
# unreliable: تعمل لكن قد تعطي معلومات غير دقيقة
# dangerous: تُعدّل ملفات حقيقية فوراً بعد موافقة

RISK_LEVELS = {
    # read_only
    Intent.PROJECT_INDEX: "read_only",
    Intent.DEPENDENCY_MAP: "read_only",
    Intent.DEPENDENTS_QUERY: "read_only",
    Intent.IMPACT_CHAIN_QUERY: "read_only",
    Intent.CRITICALITY_QUERY: "read_only",
    Intent.ENTRY_POINT_QUERY: "read_only",
    Intent.FILE_IMPACT: "read_only",
    Intent.IMPACT_ANALYSIS: "read_only",
    Intent.SPACE: "read_only",
    Intent.HEALTH: "read_only",
    Intent.STATUS: "read_only",
    Intent.HISTORY: "read_only",
    Intent.SHOW_CHANGES: "read_only",
    Intent.SESSION_SAVE: "read_only",
    Intent.CONTEXT_REPORT: "read_only",
    Intent.SYSTEM_STATUS: "read_only",
    Intent.WORK_CONTEXT: "read_only",
    Intent.AUDIT_LOG: "read_only",
    Intent.SWITCH_PROJECT: "read_only",
    Intent.RELEASE_INDEX: "read_only",
    Intent.COMPARE_VERSIONS: "read_only",
    Intent.LIST_SCRIPTS: "read_only",
    Intent.RUN_HISTORY: "read_only",
    Intent.ERROR_REPORT: "read_only",
    Intent.PENDING_FIXES: "read_only",
    Intent.MEMORY_STATUS: "read_only",
    Intent.PROJECT_TIMELINE: "read_only",
    Intent.READ_FILE: "read_only",
    Intent.CYBER_EXPLAIN: "read_only",
    Intent.CURRENT_VERSION: "read_only",
    Intent.ANALYZE_RELEASE: "read_only",
    Intent.RELEASE_INDEX: "read_only",

    # safe_write (محمي بـ safe_io)
    Intent.GENERATE_CODE: "safe_write",
    Intent.RUN_SCRIPT: "safe_write",
    Intent.DRY_RUN: "safe_write",

    # unreliable
    Intent.SEARCH_CODE: "unreliable",
    Intent.SESSION_RESTORE: "unreliable",
    Intent.PROJECT_SCAN: "unreliable",
    Intent.ANALYZE_RELEASE: "unreliable",
    Intent.ANALYZE_CODE: "unreliable",
    Intent.MODIFY_CODE: "unreliable",

    # dangerous
    Intent.REPAIR_ANALYZE: "dangerous",
    Intent.REPAIR_APPROVE: "dangerous",
    Intent.REPAIR_REJECT: "read_only",  # الرفض آمن
    Intent.CLEAN: "dangerous",
}

WARNINGS = {
    "unreliable": "⚠️ قد تحتوي هذه النتيجة معلومات غير دقيقة أو مُخمَّنة.",
    "dangerous": "🔴 تحذير: هذا الإجراء قد يُعدّل ملفات حقيقية مباشرة.",
}

def get_risk(intent: str) -> str:
    return RISK_LEVELS.get(intent, "unreliable")  # افتراضي: حذر إن لم يُصنَّف

def get_warning(intent: str) -> str:
    risk = get_risk(intent)
    return WARNINGS.get(risk, "")
