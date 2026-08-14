# CyberLab Agent v5.0.1
# intent/semantic_router.py

RULES = [
    {
        "contains": ["كل الملفات", "كل ملفات", "الملفات المتاثرة", "الملفات المتضررة"],
        "action"  : "dependency_full_closure",
        "intent"  : "dependency_map",
    },
    {
        "contains": ["رتب", "خطورة", "الاخطر", "حسب الخطر"],
        "action"  : "risk_ranking",
        "intent"  : "dependency_map",
    },
    {
        "contains": ["ما تاثير", "تاثير تعديل", "لو عدلت"],
        "action"  : "file_impact",
        "intent"  : "file_impact",
    },
    {
        "contains": ["اعرض نتيجة", "نتيجة التحليل", "اعرض التحليل"],
        "action"  : "show_last_result",
        "intent"  : "show_last_result",
    },
    {
        "contains": ["كل الاصدارات", "الاصدارات المتاحة", "قائمة اصدارات"],
        "action"  : "release_index",
        "intent"  : "release_index",
    },
    {
        "contains": ["فحص سريع", "شخص نظام", "صحة نظام"],
        "action"  : "self_diagnose",
        "intent"  : "self_diagnose",
    },
]

ALIASES = {
    "المتاثرة"  : "المتأثرة",
    "المتضررة"  : "المتأثرة",
    "ستتاثر"   : "المتأثرة",
    "المرتبطة"  : "المتأثرة",
    "الاخطاء"  : "أخطاء",
    "الثغرات"  : "ثغرات",
}

def route(text: str, current_intent: str) -> dict:
    from lab_v4_dev.intent.normalizer import normalize
    normalized = normalize(text)

    # جرب القواعد دائماً بغض النظر عن intent
    for rule in RULES:
        if any(kw in normalized for kw in rule["contains"]):
            return {
                "matched" : True,
                "action"  : rule["action"],
                "intent"  : rule["intent"],
                "original": current_intent,
            }

    # لم يجد تطابق — إذا كان project_scan وفيه كلمة ملف محدد
    import re
    if current_intent == 'project_scan' and re.search(r'[\w./]+\.py', text):
        return {"matched":True,"action":"file_impact","intent":"file_impact","original":current_intent}
    return {
        "matched" : False,
        "action"  : None,
        "intent"  : current_intent,
        "original": current_intent,
    }

def is_unsupported(intent: str, result: dict) -> bool:
    if result.get("status") in ["unsupported", "fallback"]:
        return True
    if result.get("executed") is False:
        return True
    return False
