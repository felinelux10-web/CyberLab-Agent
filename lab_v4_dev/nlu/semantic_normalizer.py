# CyberLab Agent — NLU Layer
# nlu/semantic_normalizer.py
# يحول الجمل الطبيعية إلى معانٍ موحدة محلياً بدون Groq

import json
import os
import re

BASE = os.path.dirname(__file__)

def _load_json(filename):
    path = os.path.join(BASE, filename)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def _load_patterns():
    return _load_json("language_patterns.json")

def _load_actions():
    return _load_json("semantic_actions.json")

def _load_user_language():
    return _load_json("user_language.json")

def normalize_text(text: str) -> str:
    """تطبيع النص: إزالة التشكيل والفراغات الزائدة"""
    text = text.strip()
    # حذف التشكيل
    text = re.sub(r"[\u0610-\u061A\u064B-\u065F]", "", text)
    # توحيد الهمزات
    text = re.sub(r"[أإآ]", "ا", text)
    text = re.sub(r"ة(?=\s|$)", "ه", text)
    return text

def match_pattern(text: str) -> tuple:
    """
    يبحث عن أنماط في النص.
    يعيد (semantic_action, pattern_name, confidence)
    """
    normalized = normalize_text(text)
    patterns = _load_patterns()
    actions = _load_actions()
    user_lang = _load_user_language()

    # 1. تحقق من الأنماط الشخصية أولاً (أعلى أولوية)
    for phrase, action in user_lang.get("custom_patterns", {}).items():
        if normalize_text(phrase) in normalized:
            return action, "USER_CUSTOM", 1.0

    # 2. تحقق من الأنماط العامة
    # الأولوية هنا دلالية أولاً، ثم طول العبارة.
    # الأنماط المتخصصة يجب أن تتغلب على الأنماط العامة
    # عندما تتنافس على نفس النص (مثلاً CYBER_CONCEPT مقابل EXPLAIN_COMPONENT).
    pattern_priority = {
        "CYBER_CONCEPT": 100,
        "PERSONAL_CHAT": 90,
        "EXPLAIN_COMPONENT": 10,
    }

    best_match = None
    best_priority = -1
    best_len = 0

    for pattern_name, data in patterns.items():
        priority = pattern_priority.get(pattern_name, 50)

        for phrase in data.get("patterns", []):
            norm_phrase = normalize_text(phrase)
            if norm_phrase in normalized:
                phrase_len = len(norm_phrase)

                if (
                    priority > best_priority
                    or (
                        priority == best_priority
                        and phrase_len > best_len
                    )
                ):
                    best_priority = priority
                    best_len = phrase_len
                    intent = actions.get(pattern_name, "unclear")
                    best_match = (intent, pattern_name, 0.85)

    if best_match:
        return best_match

    return None, None, 0.0

def learn_phrase(phrase: str, action: str):
    """يحفظ صيغة جديدة تعلمها من المستخدم"""
    user_lang = _load_user_language()
    user_lang.setdefault("custom_patterns", {})[phrase] = action
    user_lang.setdefault("learned_phrases", []).append(phrase)
    path = os.path.join(BASE, "user_language.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(user_lang, f, ensure_ascii=False, indent=2)

def _has_technical_context(text: str, target: str = "") -> bool:
    """
    يحدد ما إذا كان سؤال EXPLAIN_COMPONENT يحمل سياقاً تقنياً
    فعلياً، بدلاً من الاعتماد على صيغة السؤال وحدها.
    """
    normalized = normalize_text(text)
    target_normalized = normalize_text(target)

    # مؤشرات بنيوية واضحة على أن السؤال متعلق بالمشروع/الكود.
    # كلمة "ملف" وحدها لا تكفي: قد يكون السؤال عاماً عن ملف غير محدد.
    structural_signals = (
        "مجلد", "مشروع", "كود", "الكود",
        "مكون", "وحدة", "module", "code", "project",
        "class", "function", "دالة", "صنف",
        "ثغرة", "هجوم", "اختراق", "امن", "أمان",
        "بروتوكول", "sql", "csrf", "xss"
    )

    if any(signal in normalized for signal in structural_signals):
        return True

    # وجود مسار/امتداد ملف في السؤال دليل تقني مباشر.
    if re.search(r"(?:^|\\s)[~/]?[\\w./_-]+\\.[A-Za-z0-9_-]+", text):
        return True

    # "هذا الملف" / "هذا المكون" ليست أهدافاً تقنية فعلية.
    generic_targets = {
        "هذا الملف", "هذا الملف؟",
        "الملف", "الملف؟",
        "هذا المكون", "هذا المكون؟",
        "هذا المجلد", "هذا المجلد؟",
    }

    target_lower = target_normalized.strip().lower()

    if (
        target_lower
        and target_lower not in generic_targets
        and (
            target_lower.startswith(("/", "~/"))
            or "." in target_lower
            or "/" in target_lower
            or target_lower.startswith(("class ", "function "))
        )
    ):
        return True

    # بعض المصطلحات البرمجية قد لا تحمل كلمة "كود" صراحة.
    # يجب البحث عنها في السؤال الكامل، وليس في target فقط.
    technical_terms = (
        "intent detection", "task planning", "execution",
        "state management", "api", "database", "backend",
        "frontend", "python", "javascript", "json", "yaml",
        "git", "github", "gateway", "orchestrator"
    )

    normalized_lower = normalized.lower()

    return any(
        term in normalized_lower
        for term in technical_terms
    )


def analyze(text: str) -> dict:
    """
    التحليل الكامل للجملة.
    يعيد dict يحتوي intent و pattern و confidence و target
    """
    # تطبيق Language Adapter أولاً
    try:
        from lab_v4_dev.nlu.language_adapter import adapt
        adapted_text = adapt(text)
    except:
        adapted_text = text

    action, pattern, confidence = match_pattern(adapted_text)
    if not action:
        action, pattern, confidence = match_pattern(text)

    # استخراج الهدف (اسم ملف أو مكون)
    target = _extract_target(text)

    # استخراج الكيان عبر Entity Extractor

    # استخراج الكيان عبر Entity Extractor
    try:
        from lab_v4_dev.nlu.entity_extractor import extract as entity_extract
        entity = entity_extract(text, action or "")
        if entity["value"] and not target:
            target = entity["value"]
    except:
        entity = {"type": "UNKNOWN", "value": "", "confidence": 0.0}

    # EXPLAIN_COMPONENT is a question shape, not proof of a cyber subject.
    # Keep the specialized route only when the current request itself carries
    # technical/project evidence; prior conversation history is not evidence.
    if (
        pattern == "EXPLAIN_COMPONENT"
        and (target or entity.get("value"))
        and not _has_technical_context(text, target or entity.get("value", ""))
    ):
        action = _load_actions().get("PERSONAL_CHAT", "personal_chat")
        pattern = "PERSONAL_CHAT"

    return {
        "intent"    : action,
        "pattern"   : pattern,
        "confidence": confidence,
        "target"    : target,
        "entity"    : entity,
        "raw"       : text,
    }

def _extract_target(text: str) -> str:
    """استخراج اسم الملف أو المكون من الجملة"""
    # مسار كامل
    m = re.search(r"(?:^|\s)([~/][\w./_~-]+\.\w+)", text)
    if m: return m.group(1)
    # مسار نسبي
    m = re.search(r"(?<![\u0600-\u06FF])([\w][\w./:-]*\.\w+)", text)
    if m: return m.group(0)
    # بعد كلمة مفتاحية
    m = re.search(r"(?:ملف|مكون|وحدة|module|file)\s+(\S+)", text)
    if m: return m.group(1)
    return ""
