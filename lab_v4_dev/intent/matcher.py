# CyberLab Agent v4.7
# intent/matcher.py

from lab_v4_dev.intent.dictionary import DICTIONARY
from lab_v4_dev.intent.normalizer import normalize
from lab_v4_dev.intent.intents import Intent

def _build_dict():
    # نبني الـ dict في كل مرة لضمان التحديث
    # ونرتبه من الأطول للأقصر لضمان الأولوية الصحيحة
    items = [(normalize(k), v) for k, v in DICTIONARY.items()]
    items.sort(key=lambda x: len(x[0]), reverse=True)
    return items

def match(user_input: str) -> dict:
    text  = normalize(user_input)
    items = _build_dict()

    # 1. تطابق كامل
    for key, intent in items:
        if key == text:
            return {"intent":intent,"confidence":1.0,
                    "method":"exact","raw":user_input}

    # 2. تطابق جزئي — الأطول أولاً
    for key, intent in items:
        if key in text:
            return {"intent":intent,"confidence":0.8,
                    "method":"partial","raw":user_input}

    # 3. تطابق عكسي — فقط إذا النص أطول من 4 أحرف
    if len(text) >= 4:
        for key, intent in items:
            if len(key) > 4 and text in key:
                return {"intent":intent,"confidence":0.6,
                        "method":"reverse","raw":user_input}

    return {"intent":Intent.UNCLEAR,"confidence":0.0,
            "method":"none","raw":user_input}

def needs_clarification(result: dict) -> bool:
    return result["intent"] == Intent.UNCLEAR
