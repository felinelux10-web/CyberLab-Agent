# CyberLab Agent v5.1
# core/repair/fix_generator.py

from lab_v4_dev.llm.gateway import ask

FIX_SYSTEM = """أنت مبرمج متخصص في إصلاح أخطاء Python.
مهمتك: اقتراح إصلاح دقيق للخطأ.
أجب بـ JSON فقط:
{
  "fix_type": "replace_line|add_import|add_variable|restructure",
  "description": "وصف الإصلاح بالعربية",
  "original": "الكود الأصلي",
  "suggested": "الكود المقترح",
  "confidence": 0.0-1.0
}"""

def generate_fix(error: dict, analysis: dict, code: str = "") -> dict:
    # إصلاح محلي للحالات البسيطة
    local = _local_fix(error, analysis)
    if local and local["confidence"] >= 0.9:
        return local

    # استخدم Groq للحالات المعقدة
    prompt = f"""الخطأ: {error.get('message','')}
السبب: {analysis.get('root_cause','')}
التلميح: {analysis.get('fix_hint','')}
الكود:
{code[:500] if code else 'غير متاح'}

اقترح إصلاحاً دقيقاً."""

    result = ask(prompt, system=FIX_SYSTEM, max_tokens=300)
    if result["status"] != "success":
        return local or _unknown_fix()

    import json, re
    text = result.get("text","")
    m    = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    return local or _unknown_fix()

def _local_fix(error: dict, analysis: dict) -> dict:
    category = analysis.get("category","")
    message  = error.get("message","")

    if category == "dependency":
        import re
        m = re.search(r"No module named '(\S+)'", message)
        if m:
            module = m.group(1)
            return {
                "fix_type"   : "install_package",
                "description": f"تثبيت المكتبة {module}",
                "original"   : f"import {module}",
                "suggested"  : f"pip install {module}",
                "confidence" : 0.95,
                "command"    : f"pip install {module} --break-system-packages",
            }

    if category == "syntax":
        return {
            "fix_type"   : "manual_review",
            "description": "خطأ في الصياغة — راجع السطر المذكور",
            "original"   : "",
            "suggested"  : "",
            "confidence" : 0.7,
        }

    if category == "name" or "KeyError" in message:
        import re
        m = re.search(r"KeyError: [\w\W]*?(\w+)", message)
        key = m.group(1) if m else "key"
        return {
            "fix_type"   : "replace_line",
            "description": f"استبدال الوصول المباشر بـ .get('{key}', None)",
            "original"   : f'["{key}"]',
            "suggested"  : f".get('{key}', None)",
            "confidence" : 0.90,
        }

    if category == "file" or "FileNotFoundError" in message:
        import re
        m = re.search(r"No such file or directory: ['"']?(.+?)['"']?$", message)
        path_val = m.group(1) if m else "المسار"
        return {
            "fix_type"   : "add_variable",
            "description": f"أضف os.makedirs لإنشاء المجلد تلقائياً",
            "original"   : f"open('{path_val}')",
            "suggested"  : f"os.makedirs(os.path.dirname('{path_val}'), exist_ok=True)",
            "confidence" : 0.88,
        }

    if category == "type" or "TypeError" in message:
        return {
            "fix_type"   : "replace_line",
            "description": "تحويل النوع — تحقق من str() أو int() أو list()",
            "original"   : "",
            "suggested"  : "str(value) / int(value) / list(value)",
            "confidence" : 0.75,
        }

    return None

def _unknown_fix() -> dict:
    return {
        "fix_type"   : "manual_review",
        "description": "يحتاج مراجعة يدوية",
        "original"   : "",
        "suggested"  : "",
        "confidence" : 0.3,
    }

def safe_retry(file_path: str, fix: dict, executor_fn) -> dict:
    if fix.get("fix_type") == "install_package":
        import subprocess
        cmd = fix.get("command","")
        if cmd:
            r = subprocess.run(cmd.split(), capture_output=True, text=True)
            if r.returncode == 0:
                return executor_fn(file_path)
    return {"status":"needs_approval","fix":fix}
