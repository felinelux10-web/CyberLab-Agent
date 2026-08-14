# CyberLab Agent v4.6
# intent/intent_parser.py

import re
from lab_v4.intent.matcher import match
from lab_v4.intent.normalizer import normalize
from lab_v4.intent.fuzzy_normalizer import deep_normalize
from lab_v4.intent.keyword_families import match_family
from lab_v4.intent.intents import Intent

TEMPORAL_KEYWORDS = ["اخر","آخر","اخير","السابق","اليوم","امس"]
FILE_INDICATORS   = ["ملف","file","مجلد"]

def detect_context(text: str) -> str:
    if any(w in text for w in ["كاملة","الكل","شامل"]):
        return "full"
    if any(w in text for w in ["متبقي","متاح","فارغ"]):
        return "free"
    if any(w in text for w in ["مستهلك","مستخدم"]):
        return "used"
    if any(w in text for w in FILE_INDICATORS):
        return "file_operation"
    if any(w in text for w in ["مشروع","project","نظام"]):
        return "project_level"
    if any(w in text for w in ["اخر","آخر","تعديل","تغيير"]):
        return "temporal"
    return "general"

def _extract_target(text: str) -> str:
    m = re.search(r"[\w./]+\.\w+", text)
    if m:
        return m.group(0)
    m = re.search(r"(?:ملف|file)\s+(\S+)", text)
    if m:
        return m.group(1)
    return ""

def _is_temporal(word: str) -> bool:
    return any(t in normalize(word) for t in TEMPORAL_KEYWORDS)

def parse(user_input: str) -> dict:
    # 1. تطبيع عميق (يحل الأخطاء الإملائية)
    normalized_input = deep_normalize(user_input)

    # 2. جرب dictionary match
    match_result = match(normalized_input)
    intent       = match_result["intent"]
    confidence   = match_result["confidence"]

    # 3. إذا unclear → جرب keyword families
    if intent == Intent.UNCLEAR:
        family_intent = match_family(normalized_input)
        if family_intent:
            intent     = family_intent
            confidence = 0.7

    # 4. إذا لا يزال unclear → جرب النص الأصلي
    if intent == Intent.UNCLEAR:
        match_result2 = match(user_input)
        if match_result2["intent"] != Intent.UNCLEAR:
            intent     = match_result2["intent"]
            confidence = match_result2["confidence"]

    # 5. سياق زمني
    context = detect_context(normalized_input)
    if intent == Intent.UNCLEAR and context == "temporal":
        intent = Intent.SHOW_CHANGES

    # 6. استخراج الهدف
    target = _extract_target(user_input)
    if target and _is_temporal(target):
        target = None
        if intent == Intent.READ_FILE:
            intent = Intent.SHOW_CHANGES

    return {
        "intent"    : intent,
        "target"    : target,
        "context"   : context,
        "confidence": confidence,
        "raw"       : user_input,
    }
