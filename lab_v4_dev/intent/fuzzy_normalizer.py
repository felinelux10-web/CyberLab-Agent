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
    "ماهة":"ماهي","ماهو":"ما هو",
    "اسناؤها":"اسماؤها","اسناءها":"اسماؤها",
    "اسناوها":"اسماؤها","اسماوها":"اسماؤها",
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
    # Apply longer phrases first so compound corrections
    # cannot be corrupted by shorter substring replacements.
    for wrong in sorted(SOUND_MAP, key=len, reverse=True):
        result = result.replace(wrong, SOUND_MAP[wrong])

    # 4. تنظيف المسافات
    result = re.sub(r"\s+", " ", result).strip()

    return result

def similarity(a: str, b: str) -> float:
    # Normalized Levenshtein similarity.
    # Used only as a conservative fallback after exact/word matching fails.
    a, b = deep_normalize(a), deep_normalize(b)

    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))

    for i, ca in enumerate(a, 1):
        current = [i]

        for j, cb in enumerate(b, 1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (ca != cb)

            current.append(
                min(insert_cost, delete_cost, replace_cost)
            )

        previous = current

    distance = previous[-1]
    return 1.0 - (distance / max(len(a), len(b)))
