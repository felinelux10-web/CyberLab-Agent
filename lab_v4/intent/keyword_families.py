# CyberLab Agent v4.6
# intent/keyword_families.py

from lab_v4.intent.intents import Intent

FAMILIES = {
    Intent.SPACE: [
        "مساحة","مساحه","مساخة","تخزين","ذاكرة","الرام","ram",
        "متبقي","متاح","فارغ","مستهلك","مستخدم","storage",
    ],
    Intent.CLEAN: [
        "نظف","تنظيف","نظفه","ازل","احذف","حذف","تفريغ",
        "clear","clean","إزالة","مسح",
    ],
    Intent.STATUS: [
        "حال","حالة","وضع","كيف","هل","status","حاله",
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
        "اخر","آخر","تعديل","تغيير","سجل","تاريخ",
        "مهمة","نتيجة","اصدار","نسخة",
    ],
    Intent.READ_FILE: [
        "اقرأ","اقرا","اعرض","حلل ملف","افتح","ملف",
        "read","show","كود","محتوى",
    ],
    Intent.REPORT: [
        "تقرير","ملخص","report","احصاء","اكتب تقرير",
        "جلسة","انجاز",
    ],
    Intent.HISTORY: [
        "سجل","تاريخ","history","سابق","قبل","مهام",
        "عمليات","نشاط",
    ],
    Intent.CONTEXT_REPORT: [
        "سياق","استعد","استعادة","context report","تقرير السياق",
        "وين وصلنا","وين كنا","ايش عملنا","ما تم","ملخص العمل",
        "استرجع","جلسة سابقة","من البداية","تقرير كامل",
    ],
    Intent.HELP: [
        "مساعدة","help","اوامر","ماذا","قائمة","كيف استخدم",
    ],
}

def match_family(text: str) -> str | None:
    text_lower = text.lower()
    
    # أزل ال التعريف للمقارنة
    import re
    clean = re.sub(r"\bال", "", text_lower).strip()
    
    best_intent = None
    best_score  = 0
    
    for intent, keywords in FAMILIES.items():
        score = 0
        for kw in keywords:
            if kw in clean or kw in text_lower:
                score += 1
        if score > best_score:
            best_score  = score
            best_intent = intent
    
    return best_intent if best_score > 0 else None
