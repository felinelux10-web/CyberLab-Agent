# CyberLab Agent v5.1
# core/repair/error_analyzer.py

from lab_v4_dev.llm.gateway import ask
from lab_v4_dev.core.repair.error_reader import parse_traceback

ANALYZER_SYSTEM = """أنت محلل أخطاء برمجية متخصص.
مهمتك: تحليل الخطأ وتحديد السبب الحقيقي.
أجب بـ JSON فقط بدون أي نص إضافي:
{
  "root_cause": "وصف قصير للسبب",
  "category": "syntax|runtime|logic|dependency|name|type",
  "confidence": 0.0-1.0,
  "fix_hint": "تلميح قصير للإصلاح",
  "fixable": true|false
}"""

def analyze(error: dict, code_snippet: str = "") -> dict:
    error_type = error.get("type", "unknown")
    message    = error.get("message", "")
    line       = error.get("line")
    raw        = error.get("raw", "")

    # تحليل محلي للأخطاء البسيطة
    local = _local_analyze(error_type, message)
    if local["confidence"] >= 0.9:
        return local

    # استخدم Groq للأخطاء المعقدة
    prompt = f"""حلل هذا الخطأ:
نوع: {error_type}
السطر: {line}
الرسالة: {message}
الخطأ الكامل:
{raw[:500]}
"""
    if code_snippet:
        prompt += f"\nالكود:\n{code_snippet[:300]}"

    result = ask(prompt, system=ANALYZER_SYSTEM, max_tokens=200)
    if result["status"] != "success":
        return local

    import json, re
    text = result.get("text","")
    m    = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    return local

def _load_patterns() -> dict:
    import json, os
    path = "project_data/error_patterns.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def _local_analyze(error_type: str, message: str) -> dict:
    # استخدم Knowledge Base أولاً
    patterns = _load_patterns()
    for err_name, info in patterns.items():
        if err_name.lower() in message.lower():
            return {
                "root_cause": info["cause"],
                "category"  : info["category"],
                "confidence": 0.92,
                "fix_hint"  : f"راجع خطأ {err_name}",
                "fixable"   : info["fixable"],
            }
    rules = {
        "syntax"    : ("خطأ في صياغة الكود",        "syntax",     0.95, "تحقق من الأقواس والنقطتين"),
        "dependency": ("مكتبة غير مثبتة",            "dependency", 0.95, "pip install المكتبة"),
        "name"      : ("متغير أو دالة غير معرفة",    "name",       0.90, "تحقق من أسماء المتغيرات"),
        "type"      : ("نوع بيانات خاطئ",            "type",       0.85, "تحقق من أنواع البيانات"),
        "file"      : ("ملف غير موجود",              "file",       0.95, "تحقق من مسار الملف"),
        "runtime"   : ("خطأ في التنفيذ",              "runtime",    0.75, "راجع المنطق والقيم"),
    }
    if error_type in rules:
        cause, cat, conf, hint = rules[error_type]
        return {
            "root_cause": cause,
            "category"  : cat,
            "confidence": conf,
            "fix_hint"  : hint,
            "fixable"   : True,
        }
    return {
        "root_cause": "خطأ غير معروف",
        "category"  : "runtime",
        "confidence": 0.5,
        "fix_hint"  : "راجع الكود يدوياً",
        "fixable"   : False,
    }
