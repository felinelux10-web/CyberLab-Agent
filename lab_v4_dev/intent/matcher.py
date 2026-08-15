# CyberLab Agent v4.7
# intent/matcher.py

from lab_v4_dev.intent.dictionary import DICTIONARY
from lab_v4_dev.intent.normalizer import normalize
from lab_v4_dev.intent.intents import Intent
import re

def _build_dict():
    # نبني الـ dict في كل مرة لضمان التحديث
    # ونرتبه من الأطول للأقصر لضمان الأولوية الصحيحة
    items = [(normalize(k), v) for k, v in DICTIONARY.items()]
    items.sort(key=lambda x: len(x[0]), reverse=True)
    return items

def _word_search(key: str, text: str) -> bool:
    # Use Unicode-aware word boundaries to avoid substring collisions
    if not key:
        return False
    try:
        # Use Python word boundary approach but guard for unicode Arabic letters
        # Build pattern that ensures key appears as separate token
        pattern = r"(?<!\w)" + re.escape(key) + r"(?!\w)"
        return re.search(pattern, text, flags=re.UNICODE) is not None
    except re.error:
        return key in text

def match(user_input: str) -> dict:
    text  = normalize(user_input)
    items = _build_dict()

    # 1. تطابق كامل
    for key, intent in items:
        if key == text:
            return {"intent":intent,"confidence":1.0,
                    "method":"exact","raw":user_input}

    # 2. تطابق على حدود الكلمات — تجنب التطابقات الجزئية المضللة
    for key, intent in items:
        if _word_search(key, text):
            return {"intent":intent,"confidence":0.85,
                    "method":"word","raw":user_input}

    # 3. لا نستخدم تطابق عكسي عام بعد الآن — يمنع حالات الخطأ من التفاف الكلمات القصيرة

    return {"intent":Intent.UNCLEAR,"confidence":0.0,
            "method":"none","raw":user_input}

def needs_clarification(result: dict) -> bool:
    return result["intent"] == Intent.UNCLEAR
