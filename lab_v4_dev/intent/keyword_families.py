# CyberLab Agent v4.6
# intent/keyword_families.py

from lab_v4_dev.intent.intents import Intent

FAMILIES = {
    Intent.SPACE: [
        "مساحة","مساحه","مساخة","تخزين","ذاكرة","الرام","ram",
        "متاح","فارغ","مستهلك","مستخدم","storage",
    ],
    Intent.CLEAN: [
        # Keep generic clean vocabulary; avoid delete-specific verbs like "احذف" or "حذف"
        "نظف","تنظيف","نظفه","تفريغ","clear","clean","إزالة","مسح",
    ],
    Intent.STATUS: [
        "حال","حالة","وضع","كيف","status","حاله",
        "خال","خالة","خاله","وكيل","نظام",
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


def match_family(text: str) -> str | None:
    text_lower = text.lower()

    # تجاهل أسماء الملفات والمسارات أثناء تصنيف النية
    import re
    text_match = re.sub(
        r"[\w./\\-]+\.(py|ts|js|json|yaml|yml|md|txt|sh)",
        " ",
        text_lower,
        flags=re.IGNORECASE,
    )

    # أزل ال التعريف للمقارنة
    clean = re.sub(r"\bال", "", text_match).strip()

    best_intent = None
    best_score = 0

    for intent, keywords in FAMILIES.items():
        score = 0
        for kw in keywords:
            matched = False
            # Use Unicode-aware whole-token matching to avoid substring collisions
            try:
                pattern = rf"(?<!\w){re.escape(kw)}(?!\w)"
                if re.search(pattern, clean, flags=re.IGNORECASE):
                    matched = True
                elif re.search(pattern, text_match, flags=re.IGNORECASE):
                    matched = True
            except re.error:
                # Fallback to simple substring search if pattern invalid
                matched = (kw in clean) or (kw in text_match)

            if matched:
                score += 1
        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent if best_score > 0 else None
