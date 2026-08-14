# CyberLab Agent v4.5
# intent/matcher.py

from lab_v4.intent.dictionary import DICTIONARY
from lab_v4.intent.normalizer import normalize
from lab_v4.intent.intents import Intent

# نسخة منظمة من القاموس
NORMALIZED_DICT = {normalize(k): v for k, v in DICTIONARY.items()}

def match(user_input: str) -> dict:
    text = normalize(user_input)

    # 1. تطابق كامل
    if text in NORMALIZED_DICT:
        return {
            "intent"    : NORMALIZED_DICT[text],
            "confidence": 1.0,
            "method"    : "exact",
            "raw"       : user_input,
        }

    # 2. تطابق جزئي — ابحث عن مفتاح داخل النص
    for key, intent in NORMALIZED_DICT.items():
        if key in text:
            return {
                "intent"    : intent,
                "confidence": 0.8,
                "method"    : "partial",
                "raw"       : user_input,
            }

    # 3. تطابق عكسي — ابحث عن النص داخل مفتاح
    for key, intent in NORMALIZED_DICT.items():
        if text in key:
            return {
                "intent"    : intent,
                "confidence": 0.6,
                "method"    : "reverse",
                "raw"       : user_input,
            }

    # 4. غير معروف
    return {
        "intent"    : Intent.UNCLEAR,
        "confidence": 0.0,
        "method"    : "none",
        "raw"       : user_input,
    }

def needs_clarification(result: dict) -> bool:
    return result["intent"] == Intent.UNCLEAR
