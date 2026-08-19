"""
Mode Detector — Series 10-A
يصنف نوع الرسالة قبل أي معالجة.
"""

TASK_PATTERNS = [
    "افحص","اقرأ","اكتب","حلل","شغّل","شغل","نفذ","احذف",
    "انشئ","أنشئ","عدل","اعرض","ابحث","افهم","استرجع",
    "احفظ الجلسة","خريطة","تاثير","اعتماديات","خطورة",
]

SYSTEM_PATTERNS = [
    "استكمل الجلسة","احفظ الجلسة","امسح الحوار",
    "أعد التشغيل","اعد التشغيل","اعرض آخر جلسة",
    "ما اخر جلسة","ما آخر جلسة","حالة النظام",
]

DISCUSSION_PATTERNS = [
    "دعنا نناقش","ما الأفضل","ما رأيك في","نناقش",
    "ما الفرق بين","أيهما أفضل","ما الخيار",
    "تكلم معي عن","حدثني عن","حدثني حول",
    "أخبرني عن","ناقش معي","خلينا نتكلم عن",
    "لنتحدث عن","اريد ان اتكلم عن","أريد أن أتكلم عن",
]

QUESTION_PATTERNS = [
    "اشرح لي","اشرح","ما هو","ما هي","ما وظيفة","ما وظيفته",
    "ما وظيفتها","ما دور","ما دوره","ما دورها","كيف يعمل",
    "كيف تعمل","عرفني على",
    "ماذا تعرف عن",
    "ما رأيك","هل تعتقد","هل تظن","ما اقتراحك",
    "ماذا تقترح","كيف ترى","ما وجهة نظرك",

    # أسئلة التعارف
    "من أنت","من انت","ما اسمك","عرف بنفسك",
    "ماذا تستطيع","ماذا يمكنك","ما وظيفتك",
    "ما الذي تستطيع فعله","من تكون",

    # اقتراحات عامة
    "ما الذي تقترحه",
    "بماذا تنصح",
    "ما الذي تنصح",
    "اقترح علي",
    "اقترح لي",
]

FOLLOW_UP_PATTERNS = [
    "هذا","هذه","ذلك","تلك","نفسه","نفسها",
    "السابق","السابقة","الملف السابق","الحل الثاني",
    "نفس الملف","نفس الأمر","اكمل","أكمل","تابع",

    # متابعة الحوار
    "ولماذا",
    "لماذا",
    "وما علاقته",
    "ما علاقته",
    "وماذا",
    "ماذا عن",
    "هل تنصحني",
    "تنصحني",
    "ما دوره",
    "كيف يعمل",
    "ما علاقة",
    "علاقته",
    "ثم",
    "لخصهما",
    "ما دوره",
    "كيف يعمل",
    "كيف يعمل هذا",
    "ما علاقته",
    "ما علاقته بالمشروع",
    "لخصه",
    "لخصها",
]

CHAT_PATTERNS = [
    "شكراً","شكرا","مرحبا","مرحباً","كيف حالك",
    "أهلاً","اهلا","صباح","مساء","وداعاً",
]


def detect_mode(text: str) -> str:
    """
    يعيد: TASK / SYSTEM / DISCUSSION / QUESTION / FOLLOW_UP / CHAT
    """
    t = text.strip()

    # SYSTEM أولاً — أوامر تخص الوكيل نفسه
    if any(p in t for p in SYSTEM_PATTERNS):
        return "SYSTEM"

    # FOLLOW_UP — المتابعات الحوارية قبل الأسئلة
    words = t.split()
    if words and words[0] in FOLLOW_UP_PATTERNS:
        return "FOLLOW_UP"
    if any(p in t for p in FOLLOW_UP_PATTERNS):
        return "FOLLOW_UP"

    # QUESTION
    if any(p in t for p in QUESTION_PATTERNS):
        return "QUESTION"

    # DISCUSSION
    if any(p in t for p in DISCUSSION_PATTERNS):
        return "DISCUSSION"

    # TASK — explicit task language must win over incidental chat words.
    # Example: "اكتب سكريبت يطبع مرحبا" is a TASK, not CHAT.
    if any(p in t for p in TASK_PATTERNS):
        return "TASK"

    # CHAT — only when no stronger semantic/task signal exists.
    if any(p in t for p in CHAT_PATTERNS):
        return "CHAT"

    # TASK — conservative legacy default.
    return "TASK"
