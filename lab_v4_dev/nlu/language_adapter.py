# CyberLab Agent — NLU Layer
# nlu/language_adapter.py
# طبقة تطبيع اللغة — تحول الكتابة المختلفة لتمثيل موحد

import re

# ─── توحيد الهمزات ───
def normalize_hamza(text: str) -> str:
    text = re.sub(r"[أإآ]", "ا", text)
    text = re.sub(r"ؤ", "و", text)
    text = re.sub(r"ئ", "ي", text)
    return text

# ─── إزالة التشكيل ───
def remove_tashkeel(text: str) -> str:
    return re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670]", "", text)

# ─── توحيد التاء المربوطة ───
def normalize_taa(text: str) -> str:
    return re.sub(r"ة(\s|$)", r"ه\1", text)

# ─── توحيد الألف المقصورة ───
def normalize_alef_maqsoura(text: str) -> str:
    return re.sub(r"ى", "ي", text)

# ─── إزالة المسافات الزائدة ───
def normalize_spaces(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text

# ─── توحيد علامات الاستفهام ───
def normalize_punctuation(text: str) -> str:
    text = re.sub(r"[؟?]+$", "", text).strip()
    text = re.sub(r"[!]+$", "", text).strip()
    return text

# ─── توحيد أدوات الاستفهام ───
QUESTION_MAP = {
    "ماهو"  : "ما هو",
    "ماهي"  : "ما هي",
    "ماذا"  : "ما",
}

def normalize_questions(text: str) -> str:
    words = text.split()
    result = []
    for word in words:
        result.append(QUESTION_MAP.get(word, word))
    return " ".join(result)

# ─── توحيد أفعال الطلب ───
VERB_MAP = {
    "وضح"       : "اشرح",
    "فسر"       : "اشرح",
    "عرفني"     : "اشرح",
    "قل لي"     : "اشرح",
    "حدثني"     : "اشرح",
    "بين لي"    : "اشرح",
    "كمّل"      : "أكمل",
    "كمل"       : "أكمل",
    "واصل"      : "أكمل",
    "تابع"      : "أكمل",
    "استكمل"    : "أكمل",
    "لخص لي"    : "لخص",
    "اختصر"     : "لخص",
}

def normalize_verbs(text: str) -> str:
    for original, unified in VERB_MAP.items():
        if original in text:
            text = text.replace(original, unified)
    return text

# ─── التطبيع الكامل ───
def adapt(text: str) -> str:
    """يطبّق جميع طبقات التطبيع بالترتيب"""
    text = remove_tashkeel(text)
    text = normalize_hamza(text)
    text = normalize_taa(text)
    text = normalize_alef_maqsoura(text)
    text = normalize_punctuation(text)
    text = normalize_spaces(text)
    text = normalize_questions(text)
    text = normalize_verbs(text)
    text = normalize_spaces(text)
    return text
