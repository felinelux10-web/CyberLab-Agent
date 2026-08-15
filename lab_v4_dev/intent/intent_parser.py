# CyberLab Agent v4.6
# intent/intent_parser.py

import re
from lab_v4_dev.intent.matcher import match
from lab_v4_dev.intent.normalizer import normalize
from lab_v4_dev.intent.fuzzy_normalizer import deep_normalize
from lab_v4_dev.intent.keyword_families import match_family
from lab_v4_dev.intent.intents import Intent

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
    # أولاً: مسار كامل يبدأ بـ ~/ أو /
    m = re.search(r"(?:^|\s)([~/][\w./_~-]+\.\w+)", text)
    if m: return m.group(1)
    if m:
        return m.group(0)
    # ثانياً: مسار نسبي أو اسم ملف
    m = re.search(r"(?<![؀-ۿ])([\w][\w./:-]*\.\w+)", text)
    if m:
        return m.group(0)
    # ثالثاً: بعد كلمة ملف/file
    m = re.search(r"(?:ملف|file)\s+(\S+)", text)
    if m:
        return m.group(1)
    return ""

def _is_temporal(word: str) -> bool:
    return any(t in normalize(word) for t in TEMPORAL_KEYWORDS)

# مفتاح تعطيل NLU — اجعله False لتعطيل الطبقة بالكامل
NLU_ENABLED = True

def parse(user_input: str) -> dict:
    # 0. NLU Layer — فهم الأنماط اللغوية الطبيعية
    if NLU_ENABLED:
        try:
            # منع أسئلة المتابعة الحوارية من اختطافها بواسطة NLU
            followup_guard = (
                "ولماذا",
                "لماذا",
                "وما علاقته",
                "ما علاقته",
                "وماذا عن",
                "ماذا عن",
                "هل تنصحني",
                "وأيهما",
                "ثم لخص",
                "لخصهما",
            )
            if any(user_input.startswith(x) for x in followup_guard):
                raise Exception("dialogue followup bypass")

            from lab_v4_dev.nlu.semantic_normalizer import analyze as nlu_analyze
            from lab_v4_dev.nlu.context_resolver import resolve as ctx_resolve, save_state
            nlu_result = nlu_analyze(user_input)
            if nlu_result["intent"] and nlu_result["confidence"] >= 0.85:
                # Context Resolver — استكمال العناصر الناقصة
                nlu_result = ctx_resolve(nlu_result)
                target = nlu_result.get("target", "")
                # احفظ الحالة للسياق القادم
                entity = nlu_result.get("entity", {})
                entity_val = entity.get("value", "") if isinstance(entity, dict) else ""
                if entity_val:
                    save_state(nlu_result["intent"], entity_val,
                               entity.get("type", "") if isinstance(entity, dict) else "")
                return {
                    "intent"           : nlu_result["intent"],
                    "target"           : target,
                    "context"          : detect_context(user_input),
                    "confidence"       : nlu_result["confidence"],
                    "raw"              : user_input,
                    "source"           : "nlu",
                    "context_inherited": nlu_result.get("context_inherited", False),
                }
        except:
            pass

    # 1. تطبيع عميق (يحل الأخطاء الإملائية)
    normalized_input = deep_normalize(user_input)

    # 2. جرب dictionary match
    match_result = match(normalized_input)
    intent       = match_result["intent"]
    confidence   = match_result["confidence"]

    # 3. إذا unclear → جرب النص الأصلي (تطابق دقيق له أولوية)
    if intent == Intent.UNCLEAR:
        match_result2 = match(user_input)
        if match_result2["intent"] != Intent.UNCLEAR:
            intent     = match_result2["intent"]
            confidence = match_result2["confidence"]

    # 4. إذا لا يزال unclear → جرب keyword families
    if intent == Intent.UNCLEAR:
        family_intent = match_family(normalized_input)
        if family_intent:
            intent     = family_intent
            confidence = 0.7

    # 5. سياق زمني
    context = detect_context(normalized_input)

    # 6. Intent Cache (جمل فهمها Groq سابقاً)
    if intent == Intent.UNCLEAR:
        from lab_v4_dev.intent.intent_cache import get as cache_get
        cached = cache_get(user_input)
        if cached:
            intent     = cached
            confidence = 0.9

    # 7. Groq Intent Resolver (آخر محاولة)
    # منع تحويل المتابعات الحوارية إلى أوامر نظام
    dialogue_followups = (
        "ولماذا",
        "لماذا",
        "وما علاقته",
        "ما علاقته",
        "وماذا عن",
        "ماذا عن",
        "هل تنصحني",
        "وأيهما",
        "ثم لخص",
        "لخصهما",
    )

    if intent == Intent.UNCLEAR and not any(user_input.startswith(x) for x in dialogue_followups):
        from lab_v4_dev.intent.groq_intent_resolver import resolve
        intent     = resolve(user_input)
        confidence = 0.8

    # 7.5 — إذا لا يزال unclear بعد كل المحاولات → unsupported
    if intent == Intent.UNCLEAR or intent == Intent.HELP:
        intent = "unsupported"

    # 8. استخراج الهدف
    target = _extract_target(user_input)

    # 8.1 — صريح: إذا ذُكر جهاز/هاتف/المساحة فالأولوية لـ CLEAN_DEVICE
    # الكلمة هنا تُفحص بكلمات حدودية لتجنب التطابق الجزئي
    try:
        _txt_norm = normalize(user_input)
        # device indicators (whole word checks)
        device_indicators = [
            "هاتف", "الهاتف", "جهاز", "الجهاز", "جهازي",
            "مساحة", "المساحة", "المساحه", "مساحة التخزين",
            "تنظيف الهاتف", "نظف الهاتف", "نظف المساحة"
        ]
        code_indicators   = ["كود", "الكود", "مشروع", "المشروع", "project", "ملف"]

        def _has_word(w):
            # token-aware check using whitespace boundaries
            pattern = r"(?<!\S)" + re.escape(w) + r"(?!\S)"
            return bool(re.search(pattern, _txt_norm))

        # If explicit device token present, promote to CLEAN_DEVICE
        if any(_has_word(w) for w in device_indicators):
            intent = Intent.CLEAN_DEVICE

        # If explicit code/project token present, promote to CLEANUP_CODE (but do not override explicit device)
        if intent != Intent.CLEAN_DEVICE and any(_has_word(w) for w in code_indicators):
            intent = Intent.CLEANUP_CODE

        # If resolved intent is generic CLEAN but no explicit device/code target — treat as unsupported (ambiguous)
        if intent == Intent.CLEAN:
            # If target or explicit device indicator present, keep; otherwise demote to unsupported
            explicit_device = any(_has_word(w) for w in device_indicators)
            explicit_code   = any(_has_word(w) for w in code_indicators)
            if not explicit_device and not explicit_code and not target:
                intent = "unsupported"
    except Exception:
        pass

    # DNI-10: حل ضمائر الأوامر بعد سياق سابق
    if not target and user_input.strip() in ("احذفه", "احذفها", "احذفها"):
        try:
            from lab_v4_dev.nlu.context_resolver import get_last_entity
            last = get_last_entity()
            if last.get("entity"):
                target = last["entity"]
                intent = Intent.DELETE_FILE
        except Exception:
            pass

    if target and _is_temporal(target):
        target = None
        if intent == Intent.READ_FILE:
            intent = Intent.SHOW_CHANGES

    # حفظ آخر ملف/هدف للسياق القادم
    if target and intent in (Intent.READ_FILE, Intent.DELETE_FILE, Intent.ANALYZE_CODE):
        try:
            from lab_v4_dev.nlu.context_resolver import save_state
            save_state(intent, target, "file")
        except:
            pass

    return {
        "intent"    : intent,
        "target"    : target,
        "context"   : context,
        "confidence": confidence,
        "raw"       : user_input,
    }
