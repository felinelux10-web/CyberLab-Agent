# CyberLab Agent v4.6
# intent/fuzzy_normalizer.py

import re

# توحيد الحروف المتشابهة
CHAR_MAP = {
    "أ":"ا","إ":"ا","آ":"ا","ء":"",
    "ى":"ي","ة":"ه","ئ":"ي","ؤ":"و",
    "ّ":"","َ":"","ُ":"","ِ":"","ً":"","ٌ":"","ٍ":"",
}

# كلمات متشابهة صوتياً
SOUND_MAP = {
    "خال":"حال","خاله":"حاله","خالة":"حالة",
    "مساخة":"مساحة","مساحه":"مساحة",
    "الرام":"الذاكرة","رام":"ذاكرة",
    "ماهة":"ماهي","ماهو":"ما هو",
    "حللملف":"حلل ملف","اقراملف":"اقرأ ملف",
    "كيبورد":"لوحة","سيستم":"نظام",
}

def deep_normalize(text: str) -> str:
    # 1. تطبيع الحروف
    result = ""
    for ch in text:
        result += CHAR_MAP.get(ch, ch)

    # 2. إزالة ال التعريف
    result = re.sub(r"\bال", "", result)

    # 3. تطبيع الأخطاء الصوتية
    for wrong, correct in SOUND_MAP.items():
        result = result.replace(wrong, correct)

    # 4. تنظيف المسافات
    result = re.sub(r"\s+", " ", result).strip()

    return result

def similarity(a: str, b: str) -> float:
    # مسافة Levenshtein بسيطة
    a, b = deep_normalize(a), deep_normalize(b)
    if a == b:
        return 1.0
    if len(a) == 0 or len(b) == 0:
        return 0.0
    # نسبة الأحرف المشتركة
    common = sum(1 for c in a if c in b)
    return common / max(len(a), len(b))
