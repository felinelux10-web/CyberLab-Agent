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
    import re

    normalized = normalize(text)

    # Sort rules by longest contained phrase to prefer more specific rules
    def longest_kw_len(rule):
        return max((len(k) for k in rule.get("contains", [])), default=0)

    for rule in sorted(RULES, key=longest_kw_len, reverse=True):
        # check contains list sorted by length (longest first)
        for kw in sorted(rule.get("contains", []), key=lambda x: len(x), reverse=True):
            # normalize the keyword and do token-aware match
            kw_norm = normalize(kw)
            try:
                pattern = r"(?<!\w)" + re.escape(kw_norm) + r"(?!\w)"
                if re.search(pattern, normalized, flags=re.UNICODE):
                    return {
                        "matched" : True,
                        "action"  : rule["action"],
                        "intent"  : rule["intent"],
                        "original": current_intent,
                    }
            except re.error:
                # fallback to simple substring on normalized text
                if kw_norm in normalized:
                    return {
                        "matched" : True,
                        "action"  : rule["action"],
                        "intent"  : rule["intent"],
                        "original": current_intent,
                    }

    # لم يجد تطابق — إذا كان project_scan وفيه كلمة ملف محدد
    import re as _re
    if current_intent == 'project_scan' and _re.search(r'[\w./]+\.py', text):
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
