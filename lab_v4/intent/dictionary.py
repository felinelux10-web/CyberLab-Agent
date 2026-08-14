# CyberLab Agent v4.5
# intent/dictionary.py
# القاموس العربي الرسمي

from lab_v4.intent.intents import Intent

DICTIONARY = {
    "تقرير المشروع"               : Intent.PROJECT_REPORT,
    "تقرير مشروع"                 : Intent.PROJECT_REPORT,
    "تقرير كامل"                  : Intent.PROJECT_REPORT,
    "السياق"                      : Intent.CONTEXT_REPORT,
    "سياق"                        : Intent.CONTEXT_REPORT,
    "ملخص العمل"                  : Intent.CONTEXT_REPORT,
    "ملخص عمل"                    : Intent.CONTEXT_REPORT,
    "تقرير السياق"                : Intent.CONTEXT_REPORT,



    "حلل مشروع"                   : Intent.PROJECT_SCAN,
    "افهم مشروع"                  : Intent.PROJECT_SCAN,
    "افحص مشروع"                  : Intent.PROJECT_SCAN,
    "نظف هاتف"                    : Intent.CLEAN,
    "نظف جهاز"                    : Intent.CLEAN,
    "اعرض بنيه"                   : Intent.ARCHITECTURE,
    "اعرض وحدات"                  : Intent.MODULES,
    "اعرض ملفات"                  : Intent.CRITICAL_FILES,
    "ابحث في ملفات"               : Intent.SEARCH,
    "اقرا ملف"                    : Intent.READ_FILE,
    "حلل ملف"                     : Intent.READ_FILE,
    "افحص ملف"                    : Intent.READ_FILE,
    "افهم ملف"                    : Intent.READ_FILE,
    "عدل ملف"                     : Intent.MODIFY_FILE,
    "انشئ ملف"                    : Intent.CREATE_FILE,
    "احذف ملف"                    : Intent.DELETE_FILE,
    "شغل مشروع"                   : Intent.RUN_PROJECT,
    "شغل ملف"                     : Intent.RUN_FILE,
    "اختبر مشروع"                 : Intent.TEST_PROJECT,
    "اختبر ملف"                   : Intent.TEST_FILE,
    "تقرير جلسه"                  : Intent.SESSION_REPORT,
    "ملخص جلسه"                   : Intent.SESSION_REPORT,
    "اعرض مهام"                   : Intent.TODO_LIST,
    "اضف مهمه"                    : Intent.TODO_ADD,


    "ما حالة الوكيل"              : Intent.STATUS,
    "ما حالة النظام"              : Intent.STATUS,
    "ماهي حالة الوكيل"            : Intent.STATUS,
    "وضع النظام"                  : Intent.STATUS,
    "ملفات النظام"                : Intent.CRITICAL_FILES,
    "ملفات المشروع"               : Intent.PROJECT_SCAN,
    "اعرض الملفات"                : Intent.CRITICAL_FILES,
    "تعديل الكود"                 : Intent.MODIFY_FILE,
    "تفريغ"                       : Intent.CLEAN,
    "ازالة"                       : Intent.CLEAN,
    "تسريع النظام"                : Intent.CLEAN,
    "اكتب تقرير"                  : Intent.REPORT,
    "تقرير كامل"                  : Intent.PROJECT_REPORT,
    "تقرير المشروع"               : Intent.PROJECT_REPORT,
    "خلاصة المشروع"               : Intent.PROJECT_REPORT,
    "ما تم انجازه"                : Intent.PROGRESS_REPORT,
    "اين وصلنا"                   : Intent.PROGRESS_REPORT,
    "ما الذي انجزناه"             : Intent.PROGRESS_REPORT,
    "الكود"                       : Intent.READ_FILE,
    "اعرض الكود"                  : Intent.READ_FILE,
    "نجاح"                        : Intent.STATUS,
    "خلل"                         : Intent.DIAGNOSE,
    "تدقيق"                       : Intent.DIAGNOSE,
    "تغيير"                       : Intent.SHOW_CHANGES,
    "التغييرات"                   : Intent.SHOW_CHANGES,

    # ═══════════════════════════════
    # إدارة الوكيل
    # ═══════════════════════════════
    "الحالة"                      : Intent.STATUS,
    "ما وضعك"                     : Intent.STATUS,
    "ما حالك"                     : Intent.STATUS,
    "حالة النظام"                 : Intent.STATUS,
    "هل النظام يعمل"              : Intent.STATUS,
    "كيف حال الوكيل"              : Intent.STATUS,
    "ما وضع الوكيل"               : Intent.STATUS,
    "هل كل شيء بخير"              : Intent.STATUS,
    "ما المهمة الحالية"           : Intent.CURRENT_TASK,
    "ماذا تفعل الآن"              : Intent.CURRENT_TASK,
    "أوقف"                        : Intent.STOP,
    "توقف"                        : Intent.STOP,
    "أوقف التنفيذ"                : Intent.STOP,
    "تابع"                        : Intent.RESUME,
    "استمر"                       : Intent.RESUME,
    "ألغِ المهمة"                 : Intent.CANCEL,
    "إلغاء"                       : Intent.CANCEL,
    "أعد التشغيل"                 : Intent.RESTART,
    "إعادة التشغيل"               : Intent.RESTART,
    "أعد ضبط النظام"              : Intent.RESTART,
    "ما قدراتك"                   : Intent.CAPABILITIES,
    "ما الذي تستطيع فعله"         : Intent.CAPABILITIES,
    "ما أدواتك"                   : Intent.CAPABILITIES,
    "اعرض القيود"                 : Intent.CONSTRAINTS,
    "ما القيود المفروضة"          : Intent.CONSTRAINTS,
    "ما الحدود القصوى"            : Intent.CONSTRAINTS,

    # ═══════════════════════════════
    # فهم المشروع
    # ═══════════════════════════════
    "افهم المشروع"                : Intent.PROJECT_SCAN,
    "حلل المشروع"                 : Intent.PROJECT_SCAN,
    "افحص المشروع"                : Intent.PROJECT_SCAN,
    "استكشف المشروع"              : Intent.PROJECT_SCAN,
    "دراسة المشروع"               : Intent.PROJECT_SCAN,
    "تحليل المشروع"               : Intent.PROJECT_SCAN,
    "ابنِ خريطة المشروع"          : Intent.PROJECT_MAP,
    "خريطة المشروع"               : Intent.PROJECT_MAP,
    "اعرض البنية"                 : Intent.ARCHITECTURE,
    "ما بنية المشروع"             : Intent.ARCHITECTURE,
    "البنية المعمارية"             : Intent.ARCHITECTURE,
    "اعرض الوحدات"                : Intent.MODULES,
    "ما الوحدات"                  : Intent.MODULES,
    "اعرض الاعتمادات"             : Intent.DEPENDENCIES,
    "ما الاعتمادات"               : Intent.DEPENDENCIES,
    "اعرض الملفات المهمة"         : Intent.CRITICAL_FILES,
    "ما الملفات الأساسية"         : Intent.CRITICAL_FILES,
    "حدد نقطة البداية"            : Intent.ENTRYPOINT,
    "أين يبدأ البرنامج"           : Intent.ENTRYPOINT,
    "اعرض مسار التنفيذ"           : Intent.EXECUTION_FLOW,
    "ما مسار التنفيذ"             : Intent.EXECUTION_FLOW,
    "ما الغرض من المشروع"         : Intent.PROJECT_PURPOSE,
    "ما هدف المشروع"              : Intent.PROJECT_PURPOSE,

    # ═══════════════════════════════
    # بحث
    # ═══════════════════════════════
    "ابحث عن"                     : Intent.SEARCH,
    "ابحث في الملفات"             : Intent.SEARCH,
    "دوّر على"                    : Intent.SEARCH,
    "هل يوجد"                     : Intent.SEARCH,
    "أين يوجد"                    : Intent.SEARCH,
    "اعثر على الملف"              : Intent.FIND_FILE,
    "أين الملف"                   : Intent.FIND_FILE,
    "ابحث عن الملف"               : Intent.FIND_FILE,
    "اعثر على الدالة"             : Intent.FIND_FUNCTION,
    "أين الدالة"                  : Intent.FIND_FUNCTION,
    "ابحث عن الدالة"              : Intent.FIND_FUNCTION,
    "اعثر على الكلاس"             : Intent.FIND_CLASS,
    "أين الكلاس"                  : Intent.FIND_CLASS,
    "أين تستخدم"                  : Intent.FIND_USAGES,
    "من يستدعي"                   : Intent.FIND_CALLERS,
    "ابحث عن المراجع"             : Intent.FIND_REFERENCES,
    "ما الملفات المرتبطة"         : Intent.RELATED_FILES,

    # ═══════════════════════════════
    # قراءة
    # ═══════════════════════════════
    "اقرأ الملف"                  : Intent.READ_FILE,
    "افتح الملف"                  : Intent.READ_FILE,
    "اعرض الملف"                  : Intent.READ_FILE,
    "ما محتوى الملف"              : Intent.READ_FILE,
    "اعرض الكود"                  : Intent.READ_FILE,
    "اعرض الدالة"                 : Intent.READ_FUNCTION,
    "ما محتوى الدالة"             : Intent.READ_FUNCTION,
    "اعرض الكلاس"                 : Intent.READ_CLASS,
    "ما محتوى الكلاس"             : Intent.READ_CLASS,
    "اعرض التغييرات"              : Intent.SHOW_CHANGES,
    "ما الذي تغيّر"               : Intent.SHOW_CHANGES,

    # ═══════════════════════════════
    # تخطيط
    # ═══════════════════════════════
    "ضع خطة"                      : Intent.PLAN,
    "خطط للمهمة"                  : Intent.PLAN,
    "ضع خطة تنفيذ"                : Intent.PLAN,
    "قسّم المهمة"                 : Intent.DECOMPOSE,
    "جزّئ المهمة"                 : Intent.DECOMPOSE,
    "حلل التأثير"                 : Intent.IMPACT_ANALYSIS,
    "ما تأثير التغيير"            : Intent.IMPACT_ANALYSIS,
    "حلل المخاطر"                 : Intent.RISK_ANALYSIS,
    "ما المخاطر"                  : Intent.RISK_ANALYSIS,
    "اقترح الحل"                  : Intent.PROPOSE_SOLUTION,
    "ما الحل المناسب"             : Intent.PROPOSE_SOLUTION,

    # ═══════════════════════════════
    # تعديل
    # ═══════════════════════════════
    "عدّل الملف"                  : Intent.MODIFY_FILE,
    "غيّر الملف"                  : Intent.MODIFY_FILE,
    "عدّل الدالة"                 : Intent.MODIFY_FUNCTION,
    "غيّر الدالة"                 : Intent.MODIFY_FUNCTION,
    "عدّل الكلاس"                 : Intent.MODIFY_CLASS,
    "استبدل المحتوى"              : Intent.REPLACE_BODY,
    "استبدل الكود"                : Intent.REPLACE_BODY,
    "أضف دالة"                    : Intent.ADD_FUNCTION,
    "أنشئ دالة"                   : Intent.ADD_FUNCTION,
    "أضف كلاس"                    : Intent.ADD_CLASS,
    "أنشئ كلاس"                   : Intent.ADD_CLASS,
    "احذف الدالة"                 : Intent.REMOVE_FUNCTION,
    "أزل الدالة"                  : Intent.REMOVE_FUNCTION,
    "احذف الكلاس"                 : Intent.REMOVE_CLASS,
    "أنشئ ملفاً"                  : Intent.CREATE_FILE,
    "ابنِ ملفاً"                  : Intent.CREATE_FILE,
    "اكتب ملفاً"                  : Intent.CREATE_FILE,
    "احذف الملف"                  : Intent.DELETE_FILE,
    "أزل الملف"                   : Intent.DELETE_FILE,
    "انقل الملف"                  : Intent.MOVE_FILE,
    "أعد تسمية الملف"             : Intent.RENAME_FILE,

    # ═══════════════════════════════
    # إعادة هيكلة
    # ═══════════════════════════════
    "أعد هيكلة الملف"             : Intent.REFACTOR_FILE,
    "أعد هيكلة المشروع"           : Intent.REFACTOR_PROJECT,
    "نظّف الكود"                  : Intent.CLEANUP_CODE,
    "رتّب الكود"                  : Intent.CLEANUP_CODE,
    "حسّن الكود"                  : Intent.OPTIMIZE_CODE,
    "اجعل الكود أفضل"             : Intent.OPTIMIZE_CODE,
    "حدّث الكود"                  : Intent.UPGRADE_CODE,

    # ═══════════════════════════════
    # تنفيذ
    # ═══════════════════════════════
    "شغّل"                        : Intent.RUN,
    "نفّذ"                        : Intent.RUN,
    "ابدأ التنفيذ"                : Intent.RUN,
    "شغّل المشروع"                : Intent.RUN_PROJECT,
    "ابدأ المشروع"                : Intent.RUN_PROJECT,
    "شغّل الملف"                  : Intent.RUN_FILE,
    "نفّذ الملف"                  : Intent.RUN_FILE,
    "شغّل الاختبارات"             : Intent.RUN_TESTS,
    "نفّذ الاختبارات"             : Intent.RUN_TESTS,
    "أوقف التشغيل"                : Intent.STOP_EXECUTION,

    # ═══════════════════════════════
    # اختبار
    # ═══════════════════════════════
    "اختبر المشروع"               : Intent.TEST_PROJECT,
    "اختبر الملف"                 : Intent.TEST_FILE,
    "اختبر الدالة"                : Intent.TEST_FUNCTION,
    "أنشئ اختباراً"               : Intent.GENERATE_TEST,
    "اكتب اختباراً"               : Intent.GENERATE_TEST,
    "اعرض نتائج الاختبار"         : Intent.TEST_REPORT,
    "تحقق من الإصلاح"             : Intent.VERIFY_FIX,

    # ═══════════════════════════════
    # تشخيص
    # ═══════════════════════════════
    "شخّص المشكلة"                : Intent.DIAGNOSE,
    "حلل الخطأ"                   : Intent.DIAGNOSE,
    "ما المشكلة"                  : Intent.DIAGNOSE,
    "اكتشف المشكلة"               : Intent.DIAGNOSE,
    "اعرض الخطأ"                  : Intent.SHOW_ERROR,
    "ما الخطأ"                    : Intent.SHOW_ERROR,
    "اعرض السجل"                  : Intent.LOGS,
    "السجل"                       : Intent.LOGS,
    "سجل العمليات"                : Intent.LOGS,
    "ما سبب الفشل"                : Intent.FAILURE_REASON,
    "لماذا فشل"                   : Intent.FAILURE_REASON,
    "ما الملف المتسبب"            : Intent.ROOT_CAUSE,
    "أين المشكلة الأصلية"         : Intent.ROOT_CAUSE,
    "افحص النظام"                 : Intent.HEALTH,
    "شخّص النظام"                 : Intent.HEALTH,
    "فحص شامل"                    : Intent.HEALTH,
    "هل النظام سليم"              : Intent.HEALTH,
    "فحص أمني"                    : Intent.HEALTH,

    # ═══════════════════════════════
    # استرجاع
    # ═══════════════════════════════
    "أصلح المشكلة"                : Intent.AUTO_FIX,
    "أصلح الخطأ"                  : Intent.AUTO_FIX,
    "اقترح إصلاحاً"               : Intent.PROPOSE_FIX,
    "ما الحل"                     : Intent.PROPOSE_FIX,
    "استعد من الفشل"              : Intent.RECOVERY,
    "تعافَ من الخطأ"              : Intent.RECOVERY,

    "ارجع للنسخة السابقة"         : Intent.ROLLBACK,
    "عد للنسخة السابقة"           : Intent.ROLLBACK,
    "استرجع النسخة السابقة"       : Intent.ROLLBACK,
    "ارجع للحالة السابقة"         : Intent.ROLLBACK,
    "تراجع عن التغيير"            : Intent.ROLLBACK,
    "إلغاء التعديل"               : Intent.ROLLBACK,
    "استرجع النسخة"               : Intent.RESTORE_SNAPSHOT,
    "استعد النسخة"                : Intent.RESTORE_SNAPSHOT,

    # ═══════════════════════════════
    # لقطات
    # ═══════════════════════════════
    "خذ لقطة"                     : Intent.SNAPSHOT,
    "أنشئ نسخة احتياطية"          : Intent.SNAPSHOT,
    "نسخة احتياطية"               : Intent.SNAPSHOT,
    "احتفظ بنسخة"                 : Intent.SNAPSHOT,
    "اعرض اللقطات"                : Intent.LIST_SNAPSHOTS,
    "ما اللقطات المتاحة"          : Intent.LIST_SNAPSHOTS,
    "قارن اللقطات"                : Intent.COMPARE_SNAPSHOTS,
    "احذف اللقطة"                 : Intent.DELETE_SNAPSHOT,

    # ═══════════════════════════════
    # ذاكرة
    # ═══════════════════════════════
    "تذكّر"                       : Intent.REMEMBER,
    "احفظ في الذاكرة"             : Intent.REMEMBER,
    "انسَ"                        : Intent.FORGET,
    "احذف من الذاكرة"             : Intent.FORGET,
    "اعرض الذاكرة"                : Intent.MEMORY_DUMP,
    "ماذا تتذكر"                  : Intent.MEMORY_STATUS,
    "ما في ذاكرتك"                : Intent.MEMORY_STATUS,

    # ═══════════════════════════════
    # مهام
    # ═══════════════════════════════
    "أضف مهمة"                    : Intent.TODO_ADD,
    "مهمة جديدة"                  : Intent.TODO_ADD,
    "سجّل مهمة"                   : Intent.TODO_ADD,
    "إضافة مهمة"                  : Intent.TODO_ADD,
    "تذكّرني بـ"                  : Intent.TODO_ADD,
    "احذف المهمة"                 : Intent.TODO_REMOVE,
    "أزل المهمة"                  : Intent.TODO_REMOVE,
    "أنهِ المهمة"                 : Intent.TODO_COMPLETE,
    "المهمة منجزة"                : Intent.TODO_COMPLETE,
    "اعرض المهام"                 : Intent.TODO_LIST,
    "جدول المهام"                 : Intent.TODO_LIST,
    "المهام المتبقية"             : Intent.TODO_PENDING,
    "ما الذي لم ينجز"             : Intent.TODO_PENDING,

    # ═══════════════════════════════
    # تقارير
    # ═══════════════════════════════
    "تقرير السياق"                : Intent.CONTEXT_REPORT,
    "استعد السياق"                : Intent.CONTEXT_REPORT,
    "استرجع السياق"               : Intent.CONTEXT_REPORT,
    "وين وصلنا"                   : Intent.CONTEXT_REPORT,
    "وين كنا"                     : Intent.CONTEXT_REPORT,
    "ايش عملنا"                   : Intent.CONTEXT_REPORT,
    "ما تم"                       : Intent.CONTEXT_REPORT,
    "context report"              : Intent.CONTEXT_REPORT,
    "ملخص العمل"                  : Intent.CONTEXT_REPORT,
    "ملخص عمل"                    : Intent.CONTEXT_REPORT,
    "تقرير"                       : Intent.REPORT,
    "ملخص الجلسة"                 : Intent.SESSION_REPORT,
    "تقرير الجلسة"                : Intent.SESSION_REPORT,
    "ماذا فعلت اليوم"             : Intent.SESSION_REPORT,
    "ملخص المشروع"                : Intent.PROJECT_REPORT,
    "تقرير المشروع"               : Intent.PROJECT_REPORT,
    "ما الذي أنجز"                : Intent.PROGRESS_REPORT,
    "ما نسبة الإنجاز"             : Intent.PROGRESS_REPORT,
    "ما الذي تبقى"                : Intent.REMAINING_WORK,
    "ما العمل المتبقي"            : Intent.REMAINING_WORK,

    # ═══════════════════════════════
    # CyberLab خاص
    # ═══════════════════════════════
    "افهم المرجع"                 : Intent.LOAD_REFERENCE,
    "حمّل المرجع"                 : Intent.LOAD_REFERENCE,
    "قارن مع المرجع"              : Intent.COMPARE_REF,
    "هل نحن متوافقون مع المرجع"  : Intent.COMPARE_REF,
    "التزم بالمعمارية"            : Intent.ARCH_CHECK,
    "تحقق من المعمارية"           : Intent.ARCH_CHECK,
    "تحقق من الانحراف"            : Intent.DRIFT_CHECK,
    "هل انحرفنا عن المعمارية"     : Intent.DRIFT_CHECK,
    "أنشئ مختبراً"                : Intent.CREATE_LAB,
    "ابنِ مختبراً"                : Intent.CREATE_LAB,
    "حدّث المختبر"                : Intent.UPDATE_LAB,
    "أنشئ لقطة مستقرة"           : Intent.STABLE_SNAPSHOT,
    "احفظ نسخة مستقرة"           : Intent.STABLE_SNAPSHOT,
    "استرجع النسخة المستقرة"      : Intent.RESTORE_STABLE,
    "ارجع للنسخة المستقرة"        : Intent.RESTORE_STABLE,
    "تحقق من السلامة"             : Intent.INTEGRITY_CHECK,
    "فحص السلامة"                 : Intent.INTEGRITY_CHECK,

    # ═══════════════════════════════
    # نظام عام
    # ═══════════════════════════════
    "مساحة"                       : Intent.SPACE,
    "الذاكرة"                     : Intent.SPACE,
    "مساحة التخزين"               : Intent.SPACE,
    "ما المساحة المتبقية"         : Intent.SPACE,
    "نظّف"                        : Intent.CLEAN,
    "تنظيف"                       : Intent.CLEAN,
    "نظّف الهاتف"                 : Intent.CLEAN,
    "إزالة الملفات المؤقتة"       : Intent.CLEAN,
    "السجل الكامل"                : Intent.HISTORY,
    "تاريخ العمليات"              : Intent.HISTORY,
    "العمليات السابقة"            : Intent.HISTORY,
    "الجدول"                      : Intent.SCHEDULE,
    "جدولي"                       : Intent.SCHEDULE,
    "المهام المجدولة"             : Intent.SCHEDULE,
    "سجّل ملاحظة"                 : Intent.NOTE,
    "ملاحظة"                      : Intent.NOTE,
    "احفظ ملاحظة"                 : Intent.NOTE,
    "أنشئ مسودة"                  : Intent.DRAFT,
    "اكتب مسودة"                  : Intent.DRAFT,
    "مسودة"                       : Intent.DRAFT,
    "مساعدة"                      : Intent.HELP,
    "الأوامر المتاحة"             : Intent.HELP,
    "قائمة الأوامر"               : Intent.HELP,
}
