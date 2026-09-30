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
ENTITY_REFERENCE = "REFERENCE"
ENTITY_ELABORATION = "ELABORATION"

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
    "Least Privilege", "Authentication", "Authorization",
]

_REFERENCE_ANCHORS = {
    "هذا", "هذه", "ذلك", "تلك", "بهذا", "بهذه", "بذلك", "بتلك",
    "لهذا", "لهذه", "لذلك", "لتلك", "نفسه", "نفسها",
    "فيه", "عليه", "منه", "عنه", "معه", "الموضوع", "الفكرة",
    "الامر", "السابق", "السابقة",
}
_REFERENCE_FILLERS = {
    "ما", "ماذا", "المقصود", "معنى", "اشرح", "وضح", "عرفني", "لي",
    "له", "لها", "هو", "هي", "هل", "في", "عن", "بشكل", "الشرح",
    "شرح", "توضيح", "اكثر", "ابسط", "اوضح", "مبسط", "مبسطه",
    "هذا", "هذه", "ذلك", "تلك", "بهذا", "بهذه", "بذلك", "بتلك",
    "لهذا", "لهذه", "لذلك", "لتلك", "نفسه", "نفسها",
    "فيه", "عليه", "منه", "عنه", "معه", "الموضوع", "الفكرة",
    "الامر", "السابق", "السابقة",
}
_ELABORATION_MARKERS = {
    "اكثر", "ابسط", "اوضح", "تفصيلا", "تفصيل", "مبسط", "مبسطه",
    "توضيح", "بسط", "زدني", "اكمل", "تابع", "واصل",
}
_ELABORATION_FILLERS = _REFERENCE_FILLERS | {
    "بسط", "اكمل", "تابع", "واصل", "زدني", "تفصيلا", "تفصيل",
}


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"[\u0610-\u061A\u064B-\u065F]", "", str(text))
    normalized = re.sub(r"[أإآ]", "ا", normalized)
    normalized = re.sub(r"[؟،؛ـ]", " ", normalized)
    normalized = re.sub(r"[^\u0600-\u06FFA-Za-z0-9_]+", " ", normalized)
    return re.findall(r"[\u0600-\u06FF]+|[A-Za-z0-9_]+", normalized.lower())


def _is_reference_only(text: str) -> bool:
    words = _tokens(text)
    return bool(
        words
        and any(word in _REFERENCE_ANCHORS for word in words)
        and all(word in _REFERENCE_FILLERS for word in words)
    )


def _is_elaboration_only(text: str) -> bool:
    words = _tokens(text)
    return bool(
        words
        and any(word in _ELABORATION_MARKERS for word in words)
        and all(word in _ELABORATION_FILLERS for word in words)
    )

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
    m = re.search(r"(?:وحدة|مكون|module|class|دالة|function)\s+([\w_]+)", text)
    if m:
        return m.group(1)

    m = re.search(
        r"\b([a-zA-Z][a-zA-Z0-9_]{2,}(?:\.[a-zA-Z][a-zA-Z0-9_]*)?)\b",
        text,
    )
    if m:
        candidate = m.group(1)

        common = {
            "the", "and", "for", "not", "with", "from", "import",
            "this", "that", "what", "how", "does", "are", "is",
            "can", "could", "should", "would", "why", "where",
            "which", "about", "please", "show", "read", "open",
            "explain", "tell", "give", "example", "work", "works",
        }

        if candidate.lower() in common:
            return None

        if (
            "_" in candidate
            or "." in candidate
            or re.search(r"[A-Z]", candidate[1:])
        ):
            return candidate

    return None


def extract(text: str, intent: str = "") -> dict:
    """
    استخراج الكيان المناسب حسب الـ intent
    يعيد dict: {type, value, confidence}
    """
    # Report semantic references/refinements without guessing their topic.
    if _is_reference_only(text):
        return {"type": ENTITY_REFERENCE, "value": "", "confidence": 0.0}
    if _is_elaboration_only(text):
        return {"type": ENTITY_ELABORATION, "value": "", "confidence": 0.0}

    # أولاً: ابحث عن ملف دائماً
    file_entity = extract_file(text)
    if file_entity:
        return {"type": ENTITY_FILE, "value": file_entity, "confidence": 0.95}

    # ثانياً: حسب الـ intent
    if intent in ["cyber_explain", "analyze_code", "self_diagnose"]:
        concept = extract_concept(text)
        if concept:
            return {"type": ENTITY_CONCEPT, "value": concept, "confidence": 0.85}
        if intent == "cyber_explain":
            return {"type": ENTITY_UNKNOWN, "value": "", "confidence": 0.0}

    if intent in ["current_version", "release_index"]:
        version = extract_version(text)
        if version:
            return {"type": ENTITY_VERSION, "value": version, "confidence": 0.9}

    # ثالثاً: مكون عام
    component = extract_component(text)
    if component:
        return {"type": ENTITY_COMPONENT, "value": component, "confidence": 0.7}

    return {"type": ENTITY_UNKNOWN, "value": "", "confidence": 0.0}
