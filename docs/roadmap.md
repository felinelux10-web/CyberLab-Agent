# خارطة طريق CyberLab Agent (بعد v5.2.4)

## الإجماع من 3 نماذج (Claude + ChatGPT + DeepSeek + Manus)
الأمان والتتبع (Audit+Rollback) أولوية أعلى من التعميم أو root.
الفصل بين المراحل أفضل من الدمج - اختبار خطوة بخطوة.

## v5.3 — Safety & Transaction Foundation (التالي)
- دالة موحّدة safe_write(path, content):
  Audit Log + Backup تلقائي (.bak) + فحص Whitelist مسارات
- كل كتابة في النظام (Repair Engine, GENERATE_CODE) تمر عبرها
- هذا يحقق أيضاً "العقد الموحد" المقترح من Manus كأثر جانبي

## v5.4 — Generalization
- PROJECT_ROOT قابل للتبديل
- اختبار على "مشروع dummy" بسيط (3-5 ملفات) قبل أي مشروع حقيقي

## v5.5 — Multi-Project Real Test + File Manager
- اختبار فعلي على تطبيق الأمن السيبراني
- File Manager كأداة عملية مستقلة

## v5.6 — Execution Sandbox
- عزل تنفيذ الكود المولّد (proot/bwrap) قبل أي root

## v5.7 — هاتف معزول + root
- فقط بعد نجاح كل ما سبق
- بدون SIM/WiFi حقيقي (firewall مادي)

## v5.8 — Scheduler + Teaching Mode
- ميزات إنتاجية، بعد الاستقرار الكامل

## نظام التسمية (من v5.3 فصاعداً)
- v5.X = تغيير بنيوي كبير (ملف/مفهوم جديد كلياً)
- v5.X.Y = إضافة/تحسين صغير فوق بنية v5.X الموجودة
مثال: v5.3 (safe_io) -> v5.3.1 (Trust Labeling) -> v5.3.2 (SESSION_RESTORE fix)

## ملاحظة: تنظيف مؤجل
حذف stable/v5.2.x القديمة + إعداد git -> مؤجل لمرحلة "نقطة تثبيت"
بعد استقرار البنية الأساسية (تقريباً بعد v5.6/v5.7)
حتى ذلك الحين: نتقبل استهلاك المساحة الإضافي مقابل الأمان والرجوع السريع

## الإصدار القادم
v5.3.1 — Trust & Risk Labeling

## v5.5 — Real Project Validation (تحديث 2026-06-14)
(مرحلة تحقق وليس مرحلة ميزات جديدة)

v5.5.0  اختبار ai_agent (11 ملف) - هل كل الأدوات تعمل على مشروع حقيقي؟
v5.5.1  التحقق من دقة النتائج (هل الاعتماديات صحيحة فعلاً؟)
v5.5.2  اختبار cyberlab_project (57 ملف) - الاختبار الحقيقي الكبير
v5.5.3  Project Validation Suite (تحقق تلقائي: index + graph + cycles + entry points)

## v5.6+ (بعد نجاح v5.5)
v5.6    Security Layer (audit + path restrictions)
v5.7    Repair Engine Expansion
v5.8    Scheduler
v6.0    Root-Safe Experimental Runtime (هاتف معزول + root)

## معايير نجاح v5.5 (يجب اجتيازها كلها)
1. الأوامر تعمل على مشروع خارجي (لا تكسر)
2. النتائج صحيحة (تتطابق مع الكود الفعلي يدوياً)
3. لا تعود تلقائياً لـ cyberlab_agent بعد SWITCH_PROJECT
4. لا يوجد أي مسار hardcoded متبقٍ يظهر عند الاختبار
5. نجاح على مشروعين مختلفين: ai_agent + cyberlab_project

التعميم لا يُعتبر مكتملاً حتى تجتاز v5.5 بالكامل.
