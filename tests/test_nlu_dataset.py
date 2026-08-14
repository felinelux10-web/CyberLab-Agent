# CyberLab Agent — NLU Benchmark
# tests/test_nlu_dataset.py

import sys
sys.path.insert(0, "/data/data/com.termux/files/home/cyberlab_agent")
from lab_v4_dev.intent.intent_parser import parse

DATASET = [
    # ─── المشروع والسياق ───
    ("أين أصبحنا الآن",                     "work_context",    None),
    ("أين وصل المشروع",                     "work_context",    None),
    ("أين وصل تطوير الوكيل",               "work_context",    None),
    ("أين نحن من الخطة",                    "work_context",    None),
    ("ما الذي انتهينا منه",                 "work_context",    None),
    ("ما الذي بقي",                         "work_context",    None),
    ("ما المرحلة الحالية",                  "work_context",    None),
    ("في أي مرحلة نحن",                    "work_context",    None),
    ("ما الذي نعمل عليه الآن",             "work_context",    None),
    ("ما أولويتنا الآن",                    "work_context",    None),
    ("هل يوجد شيء مؤجل",                   "work_context",    None),
    ("ما أكبر مشكلة حالياً",               "work_context",    None),
    ("ما أكثر شيء ينقص الوكيل",            "work_context",    None),

    # ─── استرجاع العمل ───
    ("ذكرني بما كنا نعمل عليه",            "work_context",    None),
    ("ذكرني بالخطة",                        "work_context",    None),
    ("ذكرني بما اتفقنا عليه",              "work_context",    None),
    ("راجع آخر جلسة",                       "work_context",    None),
    ("راجع آخر تعديل",                      "work_context",    None),
    ("راجع آخر إصدار",                      "current_version", None),
    ("لخص ما فعلناه",                       "session_restore", None),
    ("أعطني ملخصاً سريعاً",                "session_restore", None),
    ("لنراجع كل شيء",                       "work_context",    None),
    ("لنبدأ من جديد",                       "session_restore", None),
    ("لنراجع قبل أن نكمل",                  "work_context",    None),

    # ─── السياق والمتابعة ───
    ("أين وصلنا في عملنا",                 "work_context",    None),
    ("أين توقفنا في آخر عمل",              "work_context",    None),
    ("ماهو آخر ملف كنا نعدل عليه",         "work_context",    None),
    ("ماهو آخر اصدار اغلقنا",              "current_version", None),
    ("ماهو آخر مشروع كنا نشتغل عليه",      "last_project",    None),
    ("ماذا كنا نشتغل على هذا المشروع",     "work_context",    None),
    ("ماذا عدلنا على هذا الملف",           "work_context",    None),
    ("ما الذي أنجزناه حتى الآن",           "work_context",    None),
    ("ما الخطوة التالية",                   "work_context",    None),
    ("أكمل من حيث توقفنا",                 "session_restore", None),

    # ─── فهم الملفات ───
    ("لماذا هذا الملف موجود",              "cyber_explain",   None),
    ("هل يمكن حذف هذا الملف",             "file_impact",     None),
    ("هل هذا الملف مهم",                   "file_impact",     None),
    ("هل يعتمد عليه النظام",               "dependencies",    None),
    ("هل هو ملف حرج",                      "file_impact",     None),
    ("أين يستخدم هذا الملف",               "dependencies",    None),
    ("من الذي يستدعيه",                    "dependencies",    None),
    ("ما الذي يعتمد عليه",                 "dependencies",    None),
    ("اشرح هذه الدالة",                    "cyber_explain",   None),
    ("اشرح هذا السطر",                     "cyber_explain",   None),
    ("ما وظيفة هذا الملف",                 "cyber_explain",   None),
    ("كيف يعمل هذا الجزء",                 "cyber_explain",   None),
    ("ما علاقة هذا الملف بالباقي",         "file_impact",     None),

    # ─── قبل التعديل ───
    ("هل هذا تعديل آمن",                   "self_diagnose",   None),
    ("هل سيؤثر على شيء آخر",              "self_diagnose",   None),
    ("ما أسوأ احتمال",                      "cyber_explain",   None),
    ("إذا عدلناه ماذا قد يحدث",            "cyber_explain",   None),
    ("هل يمكن الرجوع بسهولة",              "self_diagnose",   None),
    ("هل نختبر أولاً",                     "self_diagnose",   None),
    ("هل نراجع قبل التنفيذ",               "self_diagnose",   None),
    ("ما المخاطر المحتملة",                "cyber_explain",   None),
    ("ماهي المخاطر إذا فعلنا هذا",         "cyber_explain",   None),
    ("كيف نعرف هل سينجح هذا التعديل",      "self_diagnose",   None),
    ("يمكنك اختبار محاكاة هذا التعديل",    "self_diagnose",   None),

    # ─── التحليل ───
    ("حلل هذا المشروع",                    "project_scan",    None),
    ("حلل هذه البنية",                     "analyze_code",    None),
    ("قيم هذه المعمارية",                  "analyze_code",    None),
    ("ما رأيك في التصميم",                  "cyber_explain",   None),
    ("ما المشكلة هنا",                     "self_diagnose",   None),
    ("ما السبب الحقيقي",                   "self_diagnose",   None),
    ("ما أصل المشكلة",                     "self_diagnose",   None),
    ("ما الحل الجذري",                     "cyber_explain",   None),
    ("هل توجد طريقة أفضل",                 "cyber_explain",   None),

    # ─── الأمن السيبراني ───
    ("هل ترى ثغرات",                       "cyber_explain",   None),
    ("هل يوجد احتمال اختراق",              "cyber_explain",   None),
    ("من أين يمكن مهاجمة هذا",             "cyber_explain",   None),
    ("ما أضعف نقطة",                       "cyber_explain",   None),
    ("ما أخطر نقطة",                       "criticality_query", None),
    ("كيف أفكر مثل المهاجم",               "cyber_explain",   None),
    ("كيف أكتشف محاولة اختراق",            "cyber_explain",   None),
    ("كيف أمنع تكرارها",                   "cyber_explain",   None),
    ("هل هذه الطريقة آمنة",               "cyber_explain",   None),
    ("كيف أرفع مستوى الأمان",              "cyber_explain",   None),
    ("ما الذي يجب مراقبته",               "cyber_explain",   None),

    # ─── البرمجة ───
    ("هل الكود جيد",                       "analyze_code",    None),
    ("هل يمكن تحسينه",                    "analyze_code",    None),
    ("هل يمكن تبسيطه",                    "analyze_code",    None),
    ("هل يوجد تكرار",                      "analyze_code",    None),
    ("هل يوجد تعقيد غير ضروري",            "analyze_code",    None),
    ("كيف أجعل الكود أسرع",               "cyber_explain",   None),
    ("كيف أختبره",                         "self_diagnose",   None),
    ("هل النظام يعمل بشكل سليم",           "self_diagnose",   None),
    ("ماهي نسبة الخطأ والفشل",             "cyber_explain",   None),

    # ─── النقاش والرأي ───
    ("ما رأيك",                            "cyber_explain",   None),
    ("هل توافق",                           "repair_approve",  None),
    ("ما وجهة نظرك",                       "cyber_explain",   None),
    ("لو كنت مكاني ماذا ستفعل",            "cyber_explain",   None),
    ("ما إيجابياته",                       "cyber_explain",   None),
    ("ما سلبياته",                         "cyber_explain",   None),
    ("ما البدائل",                         "cyber_explain",   None),
    ("هل يوجد حل آخر",                    "cyber_explain",   None),
    ("هل انت متأكد من هذا",               "self_diagnose",   None),
    ("هل يمكن أن تشرح أكثر",              "cyber_explain",   None),

    # ─── التخطيط ───
    ("ما الخطة",                           "work_context",    None),
    ("كيف نقسم العمل",                    "work_context",    None),
    ("ما ترتيب التنفيذ",                   "work_context",    None),
    ("ما الأولويات",                       "work_context",    None),
    ("هل نحن مستعدون للمرحلة القادمة",     "work_context",    None),
    ("كيف ننفذ هذا بطريقة مبسطة",          "cyber_explain",   None),
    ("دعنا نبدأ العمل خطوة خطوة",          "work_context",    None),
]

passed = 0
failed = 0
failures = []

print("=== NLU Benchmark Dataset ===")
print(f"إجمالي الجمل: {len(DATASET)}")
print()

for text, expected_intent, expected_target in DATASET:
    r = parse(text)
    actual = r.get("intent", "")
    src = r.get("source", "dict")
    ok = actual == expected_intent
    if ok:
        passed += 1
    else:
        failed += 1
        failures.append((text, expected_intent, actual, src))

print(f"النتيجة: {passed}/{len(DATASET)} | ", end="")
print("✅ PASSED" if failed == 0 else f"❌ {failed} فشل")
print()

if failures:
    print("─── الجمل التي فشلت ───")
    for text, exp, act, src in failures:
        print(f"  ❌ '{text}'")
        print(f"     متوقع: {exp} | فعلي: {act} [{src}]")
