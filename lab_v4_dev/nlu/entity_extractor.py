# CyberLab Agent — NLU Layer
# nlu/entity_extractor.py
# استخراج الكيانات من الجملة (ملف، مكون، مفهوم، إصدار)

import re
import os

# ─── أنواع الكيانات ───
ENTITY_FILE      = "FILE"
ENTITY_CONCEPT   = "CONCEPT"
ENTITY_VERSION   = "VERSION"
ENTITY_COMPONENT = "COMPONENT"
ENTITY_UNKNOWN   = "UNKNOWN"

# ─── كلمات تسبق الكيان ───
FILE_PREFIXES = [
    "ملف", "file", "مجلد", "المسار", "الملف",
    "محتوى", "اقرأ", "افتح", "اعرض", "حلل", "افحص"
]

CONCEPT_PREFIXES = [
    "اشرح", "وضح", "عرفني", "ما هو", "ما هي",
    "ما مفهوم", "ما معنى", "كيف يعمل", "ما هجوم",
    "ما ثغرة", "اشرح ثغرة", "اشرح هجوم"
]

# ─── امتدادات الملفات المعروفة ───
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".md", ".txt", ".sh", ".html", ".css", ".sql",
    ".java", ".cpp", ".c", ".h", ".rs", ".go"
}

# ─── مفاهيم الأمن السيبراني ───
SECURITY_CONCEPTS = [
    "SQL Injection", "XSS", "CSRF", "Buffer Overflow",
    "Man in the Middle", "Brute Force", "Phishing",
    "Ransomware", "Malware", "Backdoor", "Exploit",
    "Zero Day", "DoS", "DDoS", "Spoofing", "Sniffing",
    "Privilege Escalation", "Path Traversal", "RCE",
    "Cross Site Scripting", "Command Injection",
]

def extract_file(text: str) -> str | None:
    """استخراج اسم الملف أو المسار"""
    # مسار كامل مع ~ أو /
    m = re.search(r"(?:^|\s)([~/][\w./_~-]+\.\w+)", text)
    if m: return m.group(1).strip()

    # مسار نسبي مع امتداد معروف
    m = re.search(r"([\w][\w./:-]*\.(?:py|js|ts|json|yaml|yml|md|sh|html|css|sql))", text)
    if m: return m.group(1)

    # بعد كلمة ملف/file
    m = re.search(r"(?:ملف|file|الملف)\s+(\S+)", text)
    if m:
        candidate = m.group(1)
        if "." in candidate:
            return candidate

    return None

def extract_concept(text: str) -> str | None:
    """استخراج المفهوم أو المصطلح التقني"""
    # تحقق من مفاهيم الأمن المعروفة
    text_lower = text.lower()
    for concept in SECURITY_CONCEPTS:
        if concept.lower() in text_lower:
            return concept

    # بعد كلمات الشرح
    for prefix in CONCEPT_PREFIXES:
        if prefix in text:
            idx = text.find(prefix) + len(prefix)
            rest = text[idx:].strip()
            if rest and len(rest) > 2:
                # خذ أول 4 كلمات
                words = rest.split()[:4]
                return " ".join(words)

    return None

def extract_version(text: str) -> str | None:
    """استخراج رقم الإصدار"""
    m = re.search(r"v?\d+\.\d+[\w.]*", text)
    if m: return m.group(0)
    return None

def extract_component(text: str) -> str | None:
    """استخراج اسم المكون أو الوحدة"""
    # أسماء Python modules/files بدون امتداد
    m = re.search(r"(?:وحدة|مكون|module|class|دالة|function)\s+([\w_]+)", text)
    if m: return m.group(1)

    # كلمات تبدو كأسماء مكونات (snake_case أو camelCase)
    m = re.search(r"\b([a-zA-Z][a-zA-Z0-9_]{2,}(?:\.[a-zA-Z][a-zA-Z0-9_]*)?)\b", text)
    if m:
        candidate = m.group(1)
        # تجاهل الكلمات الإنجليزية الشائعة
        common = {"the", "and", "for", "not", "with", "from", "import"}
        if candidate.lower() not in common:
            return candidate

    return None

def extract(text: str, intent: str = "") -> dict:
    """
    استخراج الكيان المناسب حسب الـ intent
    يعيد dict: {type, value, confidence}
    """
    # أولاً: ابحث عن ملف دائماً
    file_entity = extract_file(text)
    if file_entity:
        return {"type": ENTITY_FILE, "value": file_entity, "confidence": 0.95}

    # ثانياً: حسب الـ intent
    if intent in ["cyber_explain", "analyze_code", "self_diagnose"]:
        concept = extract_concept(text)
        if concept:
            return {"type": ENTITY_CONCEPT, "value": concept, "confidence": 0.85}

    if intent in ["current_version", "release_index"]:
        version = extract_version(text)
        if version:
            return {"type": ENTITY_VERSION, "value": version, "confidence": 0.9}

    # ثالثاً: مكون عام
    component = extract_component(text)
    if component:
        return {"type": ENTITY_COMPONENT, "value": component, "confidence": 0.7}

    return {"type": ENTITY_UNKNOWN, "value": "", "confidence": 0.0}
