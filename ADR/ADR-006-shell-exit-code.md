# ADR-006 — Shell Exit Code Handling
# CyberLab Agent v4.0

## المشكلة

shell_runner يعتبر أي أمر منتهي بدون timeout ناجحاً
بغض النظر عن exit code.

مثال:
  ls /nonexistent → code: 2 → status: done (خطأ)

## القرار

تعريف النجاح الحقيقي لأمر shell:
  status: ok   → exit code == 0
  status: failed → exit code != 0

## التعديل المطلوب في shell_runner.py

    if result.returncode != 0:
        return {
            "status": "failed",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "code"  : result.returncode,
        }

## التأثير

- أوامر فاشلة ستُسجَّل كـ failed
- state.record_failure() سيُستدعى
- بعد 3 فشل متتالي → safe mode

## الأولوية

منخفضة — النظام يعمل بشكل مقبول حالياً
يُنفَّذ في الجلسة القادمة
