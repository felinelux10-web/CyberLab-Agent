# CyberLab Agent v4.7
# context/context_resolver.py

from lab_v4_dev.intent.intents import Intent

RESULT_KEYWORDS  = ["اعرض نتيجة","اكتب نتيجة","ما النتيجة","اعرض النتائج"]
REPEAT_KEYWORDS  = ["كرر","اعد","مرة ثانية","مرة اخرى"]
COMPARE_KEYWORDS = ["قارن","مقارنة","الفرق","اختلاف"]
REF_WORDS        = ["فيه","منه","عنه","معه","هذا","هذه","نفس","السابق"]

def bind_context(intent: str, text: str, store) -> dict:
    resolved = store.resolve(text)

    if any(kw in text for kw in RESULT_KEYWORDS):
        return {"intent":"show_last_result","target":store.last_target,
                "data":store.last_result,"subject":resolved["subject"]}

    if any(kw in text for kw in REPEAT_KEYWORDS):
        return {"intent":store.last_intent or intent,"target":store.last_target,
                "data":None,"subject":resolved["subject"]}

    # DNI-10: تفعيل فقط إذا كانت النية المُحلَّلة أصلاً مقارنة أو غير معروفة —
    # يمنع اختطاف نوايا أخرى ناجحة (مثل قراءة ملف) لمجرد ورود كلمة "قارن" في جملة مركبة
    _compare_intents = (Intent.COMPARE_SNAPSHOTS, Intent.COMPARE_REF,
                         Intent.COMPARE_VERSIONS, Intent.COMPARE_FILES)
    if any(kw in text for kw in COMPARE_KEYWORDS) and (
        intent in _compare_intents or intent == Intent.UNCLEAR
    ):
        _cmp_intent = intent if intent == Intent.COMPARE_FILES else Intent.COMPARE_VERSIONS
        return {"intent":_cmp_intent,"target":text,
                "subject":resolved["subject"],"version":resolved["version"]}

    if resolved["is_reference"] and resolved["subject"]:
        return {"intent":intent,"target":resolved["subject"],
                "subject":resolved["subject"],"version":resolved["version"],
                "injected":True}

    if intent == Intent.UNCLEAR:
        return {"intent":"unsupported","target":None,
                "subject":resolved["subject"]}

    return {"intent":intent,"target":None,
            "subject":resolved["subject"],"version":resolved["version"]}
