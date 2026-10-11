# CyberLab Agent v4.6
# intent/keyword_families.py

from lab_v4_dev.intent.intents import Intent

# Device RAM is classified separately; SPACE describes storage capacity.
FAMILIES = {
    Intent.SPACE: [
        "مساحة","مساحه","مساخة","تخزين",
        "متاح","فارغ","مستهلك","مستخدم","storage",
    ],
    Intent.CLEAN: [
        # Keep generic clean vocabulary; avoid delete-specific verbs like "احذف" or "حذف"
        "نظف","تنظيف","نظفه","تفريغ","clear","clean","إزالة","مسح",
    ],
    Intent.STATUS: [
        "حال","حالة","وضع","status","حاله",
        "خال","خالة","خاله",
    ],
    Intent.HEALTH: [
        "صحة","فحص","شخص","تشخيص","سليم","يعمل","بطيء",
        "health","check","مشكلة","خلل",
    ],
    Intent.PROJECT_SCAN: [
        "مشروع","project","ملفات","بنية","هيكل","cyberlab",
        "وصلنا","انجزنا","تقدم","نظرة",
    ],
    Intent.SHOW_CHANGES: [
        "تعديل","تغيير","اعرض التغييرات","ما الذي تغير",
        "نسخة",
    ],
    Intent.READ_FILE: [
        "اقرأ","اقرا","اعرض","حلل ملف","افتح","ملف",
        "read","show","محتوى",
    ],
    Intent.REPORT: [
        "تقرير","ملخص","report","احصاء","اكتب تقرير",
        "جلسة","انجاز",
    ],
    Intent.HISTORY: [
        "سجل","تاريخ","history","سابق","قبل","مهام",
        "عمليات","نشاط",
    ],
    Intent.REMAINING_TASKS: [
        "متبقي","مهام متبقية","ما تبقى","باقي",
        "لم ينجز","غير مكتمل","remaining",
    ],
    Intent.WORK_STATUS: [
        "خطة عمل","وضع عمل","ما نعمل","انجزنا",
        "ما اكتمل","تقدم عمل","work status",
    ],
    Intent.NEXT_TASK: [
        "التالي","مهمة تالية","ما التالي","next",
        "ماذا بعد","الخطوة التالية",
    ],
    Intent.ANALYZE_RELEASE: [
        "اصدار","إصدار","حلل اصدار","تقرير اصدار",
        "release","version","v4","نسخة قديمة",
    ],
    Intent.COMPARE_VERSIONS: [
        "قارن","مقارنة","فرق","اختلاف","تغير",
        "compare","diff","بين اصدار",
    ],
    Intent.RELEASE_INDEX: [
        "كل اصدارات","قائمة اصدارات","الاصدارات",
        "كم اصدار","عدد الاصدارات",
    ],
    Intent.CONTEXT_REPORT: [
        "سياق","استعد","استعادة","context report","تقرير السياق",
        "وين وصلنا","وين كنا","ايش عملنا","ما تم","ملخص العمل",
        "استرجع","جلسة سابقة","من البداية","تقرير كامل",
    ],
    Intent.WORK_CONTEXT: [
        "ماذا فعلنا","ماذا حدث","ماذا أنجزنا","ماذا انجزنا",
        "آخر عمل","ماذا لدينا يوم","ما جديد","ما الذي تم",
    ],
    Intent.HELP: [
        "مساعدة","help","اوامر","قائمة","كيف استخدم","كيف اسوي",
    ],
}


def _contains_phrase(text: str, phrases: tuple[str, ...] | list[str]) -> bool:
    import re
    from lab_v4_dev.intent.normalizer import normalize

    normalized_text = normalize(str(text or "")).casefold()
    for phrase in phrases:
        normalized_phrase = normalize(str(phrase or "")).casefold().strip()
        if not normalized_phrase:
            continue
        pattern = r"(?<!\w)" + r"\s+".join(
            re.escape(part) for part in normalized_phrase.split()
        ) + r"(?!\w)"
        if re.search(pattern, normalized_text, flags=re.UNICODE):
            return True
    return False


def _starts_with_phrase(text: str, phrases: tuple[str, ...] | list[str]) -> bool:
    from lab_v4_dev.intent.normalizer import normalize

    normalized_text = normalize(str(text or "")).casefold().strip()
    request_prefixes = (
        "لو سمحت", "من فضلك", "رجاء", "يرجى", "اريد", "اعطني", "please",
    )
    for phrase in phrases:
        normalized_phrase = normalize(str(phrase or "")).casefold().strip()
        if not normalized_phrase:
            continue
        if (
            normalized_text == normalized_phrase
            or (
                normalized_text.startswith(normalized_phrase)
                and len(normalized_text) > len(normalized_phrase)
                and (
                    normalized_text[len(normalized_phrase)].isspace()
                    or normalized_text[len(normalized_phrase)] in "؟?!.،,;:"
                )
            )
        ):
            return True
        for prefix in request_prefixes:
            normalized_prefix = normalize(prefix).casefold()
            if normalized_text.startswith(normalized_prefix + " "):
                remainder = normalized_text[len(normalized_prefix):].strip()
                if (
                    remainder == normalized_phrase
                    or (
                        remainder.startswith(normalized_phrase)
                        and len(remainder) > len(normalized_phrase)
                        and (
                            remainder[len(normalized_phrase)].isspace()
                            or remainder[len(normalized_phrase)] in "؟?!.،,;:"
                        )
                    )
                ):
                    return True
    return False


def _family_request_allowed(intent: str, text: str, clean: str) -> bool:
    """A topic noun alone is not enough to authorize a routed operation."""
    import re

    tokens = set(re.findall(r"[\w]+", clean, flags=re.UNICODE))
    meta_markers = {
        "كلمه", "الكلمه", "مصطلح", "المصطلح", "عباره", "العباره",
        "لفظ", "اللفظ", "معنى", "المعنى",
    }
    if tokens & meta_markers:
        return False

    storage_terms = {
        "مساحه", "مساحة", "تخزين", "storage", "الهاتف", "هاتف", "الجهاز",
        "جهاز", "phone", "device", "المتبقي", "متبقي", "المتاح", "متاح",
        "الفارغ", "فارغ", "free", "available", "used", "total",
    }
    clean_actions = {
        "نظف", "تنظيف", "نظفه", "تفريغ", "مسح", "clear", "clean",
    }

    if intent == Intent.SPACE:
        # Require storage-specific grammar, not a general opinion/question
        # that happens to contain the noun "space".
        exact_storage_queries = {
            "مساحة الهاتف", "مساحه الهاتف", "مساحه هاتف",
            "مساحة الجهاز", "مساحه الجهاز", "مساحه جهاز",
            "مساحة التخزين", "مساحه التخزين", "مساحه تخزين",
            "مساحة الهاتف؟", "مساحة الجهاز؟",
        }
        if (
            clean.strip(" ؟?!.،,") in exact_storage_queries
            or text.strip(" ؟?!.،,") in exact_storage_queries
        ):
            return True
        if tokens & {"راي", "رايي", "رأيي"}:
            return False
        return bool(tokens & storage_terms) and _starts_with_phrase(text, (
            "كم المساحه", "كم مساحة", "كم مساحه", "ما المساحه", "ما مساحة",
            "ما مساحه", "كم التخزين", "كم تخزين", "المساحه المتبقيه",
            "المتاح من التخزين", "اعرض المساحه", "اعرض مساحة", "اعرض مساحه",
            "افحص المساحه", "افحص مساحة", "show storage", "storage space",
        ))

    if intent == Intent.PROJECT_SCAN:
        return _starts_with_phrase(text, (
            "حلل المشروع", "حلل هذا المشروع", "حلل مشروع",
            "افحص المشروع", "افحص هذا المشروع", "افحص مشروع",
            "اعرض المشروع", "اعرض ملفات المشروع", "خريطة المشروع",
            "هيكل المشروع", "بنية المشروع", "حلل project", "analyze project",
            "scan project", "كم عدد ملفات المشروع", "عدد ملفات المشروع",
            "كم ملف في المشروع",
        ))

    if intent == Intent.CLEAN:
        return bool(tokens & clean_actions)

    if intent == Intent.READ_FILE:
        return _starts_with_phrase(text, (
            "اقرا الملف", "اقرأ الملف", "اعرض الملف", "اعرض ملف",
            "افتح الملف", "افتح ملف", "ما محتوى الملف", "ما داخل الملف",
            "read file", "show file", "open file",
        ))

    if intent == Intent.SHOW_CHANGES:
        return _starts_with_phrase(text, (
            "اعرض التغييرات", "اعرض التغيير", "ما الذي تغير",
            "ماذا تغير", "اخر تعديل", "آخر تعديل", "راجع اخر تعديل",
            "راجع آخر تعديل", "show changes", "view diff",
        ))

    if intent == Intent.HISTORY:
        return _starts_with_phrase(text, (
            "سجل التعديلات", "تاريخ التعديلات", "سجل العمل",
            "ابحث في السجل", "اعرض السجل", "ماذا تغير سابقا",
            "history log", "show history",
        ))

    if intent == Intent.STATUS:
        return _starts_with_phrase(text, (
            "حالة النظام", "ما حالة النظام", "ما حاله النظام",
            "وضع النظام", "ما وضع النظام", "كيف حال النظام",
            "حالة الوكيل", "وضع الوكيل", "system status", "agent status",
        ))

    if intent == Intent.HEALTH:
        return _starts_with_phrase(text, (
            "هل النظام سليم", "هل النظام يعمل بشكل سليم",
            "افحص صحة النظام", "فحص صحة النظام", "شخص مشكلة النظام",
            "check health", "diagnose system",
        ))

    if intent == Intent.REPORT:
        return _starts_with_phrase(text, (
            "اعطني تقرير", "أعطني تقرير", "تقرير كامل",
            "ملخص الجلسة", "لخص ما فعلناه", "show report", "full report",
        ))

    if intent == Intent.HELP:
        return (
            clean.strip(" ؟?!.،,") in {"مساعده", "help", "ساعدني"}
            or text.strip(" ؟?!.،,") in {"مساعدة", "مساعده", "help", "ساعدني"}
        )

    if intent == Intent.CONTEXT_REPORT:
        return _starts_with_phrase(text, (
            "سياق العمل", "تقرير السياق", "ملخص العمل", "استرجع الجلسة",
            "تقرير كامل", "وين وصلنا", "وين كنا", "context report",
        ))

    if intent == Intent.WORK_STATUS:
        return _starts_with_phrase(text, (
            "خطة عمل", "وضع عمل", "ما نعمل", "ما الذي نعمل عليه",
            "ما الذي نشتغل عليه", "ما اكتمل", "تقدم عمل", "work status",
            "أين وصلنا", "اين وصلنا", "ما الخطوة التالية",
            "ما الأولويات", "ما الاولويات", "ماذا أنجزنا", "ماذا انجزنا",
        ))

    if intent == Intent.REMAINING_TASKS:
        return _starts_with_phrase(text, (
            "ما تبقى", "مهام متبقية", "مهام متبقيه", "لم ينجز",
            "غير مكتمل", "remaining tasks",
        ))

    if intent == Intent.NEXT_TASK:
        return _starts_with_phrase(text, (
            "ما التالي", "ماذا بعد", "الخطوة التالية", "مهمة تالية",
            "next step",
        ))

    if intent == Intent.COMPARE_VERSIONS:
        return bool(tokens & {"قارن", "مقارنة", "فرق", "اختلاف", "compare", "diff"}) and bool(
            tokens & {"اصدار", "إصدار", "نسخه", "نسخة", "version", "release", "بين"}
        )

    # Multi-word, explicitly phrased families remain available. Single-word
    # incidental matches are not enough to change the route.
    return _contains_phrase(text, tuple(
        keyword for keyword in FAMILIES.get(intent, [])
        if len(str(keyword).split()) >= 2
    ))


def match_family(text: str) -> str | None:
    text_lower = str(text or "").lower()

    # Ignore file names/paths while matching semantic families.
    import re
    text_match = re.sub(
        r"[\w./\\-]+\.(py|ts|js|json|yaml|yml|md|txt|sh)",
        " ",
        text_lower,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\bال", "", text_match).strip()

    best_intent = None
    best_score = 0

    for intent, keywords in FAMILIES.items():
        score = 0
        for kw in keywords:
            try:
                pattern = rf"(?<!\w){re.escape(kw)}(?!\w)"
                matched = bool(
                    re.search(pattern, clean, flags=re.IGNORECASE)
                    or re.search(pattern, text_match, flags=re.IGNORECASE)
                )
            except re.error:
                matched = (kw in clean) or (kw in text_match)
            if matched:
                score += 1
        if score > best_score and _family_request_allowed(intent, text_match, clean):
            best_score = score
            best_intent = intent

    return best_intent if best_score > 0 else None
