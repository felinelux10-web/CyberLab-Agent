# CyberLab Agent v4.6
# intent/intent_parser.py

import re
from lab_v4_dev.intent.matcher import match as dict_match
from lab_v4_dev.intent.normalizer import normalize
from lab_v4_dev.intent.fuzzy_normalizer import deep_normalize
from lab_v4_dev.intent.keyword_families import match_family
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.intent.intent_contract import IntentResult
from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.nlu.conversation_semantics import (
    classify_conversation_semantics,
    should_override_with_personal_chat,
)

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
    if m:
        return m.group(1)
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


def _token_has_word(text_norm: str, w: str) -> bool:
    try:
        pattern = r"(?<!\w)" + re.escape(w) + r"(?!\w)"
        return bool(re.search(pattern, text_norm, flags=re.UNICODE))
    except re.error:
        return w in text_norm


_SOFT_CONVERSATION_INTENTS = {
    Intent.UNCLEAR,
    Intent.PERSONAL_CHAT,
    Intent.UNSUPPORTED,
    Intent.HELP,
    Intent.STATUS,
    Intent.SYSTEM_STATUS,
    Intent.CYBER_EXPLAIN,
    Intent.CONTEXT_REPORT,
    Intent.WORK_CONTEXT,
}


def _early_conversation_result(user_input: str) -> dict | None:
    """Accept a strong social/style signal before broad NLU families run."""
    signal = classify_conversation_semantics(user_input)
    mode = detect_mode(user_input)
    target = _extract_target(user_input)
    if not should_override_with_personal_chat(
        user_input,
        signal,
        mode=mode,
        target=target,
    ):
        return None

    # Exact/word dictionary operations and explicit targets retain authority.
    # Weak semantic/fuzzy matches such as "STATUS" for a personal question do
    # not override a clear conversational act.
    deterministic = dict_match(user_input)
    if (
        deterministic.get("method") in {"exact", "word"}
        and deterministic.get("intent") not in _SOFT_CONVERSATION_INTENTS
    ):
        return None

    act = signal.get("conversation_act", "")
    entity_type = "ELABORATION" if act in {
        "SIMPLIFICATION_REQUEST",
        "VERBOSITY_REQUEST",
        "FORMALITY_REQUEST",
        "TONE_REQUEST",
        "STYLE_REQUEST",
    } else "UNKNOWN"
    return {
        "intent": Intent.PERSONAL_CHAT,
        "target": "",
        "context": detect_context(user_input),
        "confidence": float(signal.get("confidence", 0.6)),
        "raw": user_input,
        "source": "conversation_semantics",
        "entity_type": entity_type,
        "semantic_pattern": "",
        "conversation_domain": signal.get("conversation_domain", "social"),
        "conversation_act": act,
        "conversation_confidence": float(signal.get("confidence", 0.6)),
        "response_attributes": dict(signal.get("response_attributes") or {}),
    }



# ============================================================
# P04 / Canonical Intent Contract Boundary
# ============================================================

def _interpret(user_input: str, *, context_entity: dict | None = None) -> dict:
    # --- Early deterministic detectors (high precedence) ---
    try:
        raw = user_input.strip()
        # Comparison patterns: قارن X و Y, قارن بين X و Y, مقارنة X و Y, ما الفرق بين X و Y
        if re.search(r"\b(قارن|قارن بين|مقارنة|ما الفرق بين|الفرق بين|قارن الملف|قارن ملف)\b", raw):
            files = re.findall(r"[\w./]+\.\w+", raw)
            if len(files) >= 2:
                # Route to COMPARE_FILES and keep raw for orchestrator to extract operands
                return {
                    "intent": Intent.COMPARE_FILES,
                    "target": "",
                    "context": detect_context(raw),
                    "confidence": 0.95,
                    "raw": user_input,
                }
        # Existence patterns: هل يوجد ملف X, هل X موجود, هل الملف X موجود
        if re.search(r"\bهل\s+يوجد\b|\bهل\b.*\bموجود\b|\bهل\s+هناك\b", raw):
            files = re.findall(r"[\w./]+\.\w+", raw)
            if files:
                # Treat as a project search/existence check — SEARCH_CODE returns text
                return {
                    "intent": Intent.SEARCH_CODE,
                    "target": files[0],
                    "context": detect_context(raw),
                    "confidence": 0.90,
                    "raw": user_input,
                }
    except Exception:
        pass

    if re.search(r"^(احذف|حذف|امسح) الملف$", raw): return {"intent": Intent.DELETE_FILE, "target": "", "context": detect_context(raw), "confidence": 0.99, "raw": user_input}

    conversational_result = _early_conversation_result(user_input)
    if conversational_result is not None:
        return conversational_result

    semantic_pattern = None
    entity_type = ""

    # 0. NLU Layer — فهم الأنماط اللغوية الطبيعية
    if NLU_ENABLED:
        try:
            from lab_v4_dev.nlu.semantic_normalizer import analyze as nlu_analyze
            from lab_v4_dev.nlu.context_resolver import resolve as ctx_resolve, save_state
            nlu_result = nlu_analyze(user_input)
            semantic_pattern = nlu_result.get("pattern")
            entity = nlu_result.get("entity", {})
            if isinstance(entity, dict):
                entity_type = entity.get("type", "")
            # PERSONAL_CHAT is a deliberate conversational classification.
            # Do not discard it merely because its confidence is below the
            # technical-intent threshold; otherwise later resolver/family
            # layers can hijack ordinary conversation.
            _nlu_intent = nlu_result.get("intent")
            _nlu_confidence = nlu_result.get("confidence", 0)

            if (
                _nlu_intent == Intent.PERSONAL_CHAT
                or (
                    _nlu_intent
                    and _nlu_confidence >= 0.85
                )
            ):
                # Context Resolver — استكمال العناصر الناقصة
                nlu_result = ctx_resolve(
                    nlu_result,
                    previous_entity=context_entity,
                )
                if nlu_result.get("context_inherited") and context_entity:
                    entity_type = context_entity.get("entity_type", entity_type)

                # Save resolved entity state as before
                entity = nlu_result.get("entity", {})
                entity_val = entity.get("value", "") if isinstance(entity, dict) else ""
                if entity_val:
                    save_state(nlu_result["intent"], entity_val,
                               entity.get("type", "") if isinstance(entity, dict) else "")

                # Before accepting NLU, prefer deterministic / explicit signals
                # 1) If dictionary (exact/word) finds a mapping, prefer it
                dict_result = dict_match(user_input)
                if dict_result.get("method") != "none":
                    chosen_intent = dict_result["intent"]
                    chosen_conf   = dict_result["confidence"]
                else:
                    # 2) Token-aware explicit target checks (device / code / file)
                    _txt_norm = normalize(user_input)
                    device_indicators = [
                        "هاتف", "الهاتف", "جهاز", "الجهاز", "جهازي",
                        "مساحة", "المساحة", "المساحه", "مساحة التخزين",
                        "تنظيف الهاتف", "نظف الهاتف", "نظف المساحة"
                    ]
                    code_indicators   = ["كود", "الكود", "مشروع", "المشروع", "project", "ملف"]

                    def _has_word(w):
                        try:
                            pattern = r"(?<!\w)" + re.escape(w) + r"(?!\w)"
                            return bool(re.search(pattern, _txt_norm, flags=re.UNICODE))
                        except re.error:
                            return w in _txt_norm

                    chosen_intent = nlu_result["intent"]
                    chosen_conf   = nlu_result.get("confidence", 0.0)

                    # promote to clean_device if explicit device token present
                    if any(_has_word(w) for w in device_indicators):
                        chosen_intent = Intent.CLEAN_DEVICE
                    else:
                        # Only promote to cleanup_code when NLU implies a cleaning action
                        clean_indicators = ["نظف", "تنظيف", "نظفه", "نظّف", "مسح", "إزالة", "تفريغ", "clean", "clear"]
                        if any(_token_has_word(_txt_norm, c) for c in clean_indicators) or chosen_intent == Intent.CLEAN:
                            if any(_has_word(w) for w in code_indicators):
                                chosen_intent = Intent.CLEANUP_CODE

                    # if NLU says a delete action but there's an explicit file target -> DELETE_FILE
                    if re.search(r"\bاحذ?ف\b", _txt_norm) and (any(_has_word(w) for w in FILE_INDICATORS) or _extract_target(user_input)):
                        chosen_intent = Intent.DELETE_FILE

                return {
                    "intent"           : chosen_intent,
                    "target"           : nlu_result.get("target", ""),
                    "context"          : detect_context(user_input),
                    "confidence"       : chosen_conf,
                    "raw"              : user_input,
                    "source"           : "nlu",
                    "context_inherited": nlu_result.get("context_inherited", False),
                    "entity_type"      : entity_type,
                    "semantic_pattern" : semantic_pattern,
                }
        except Exception:
            pass

    # 1. تطبيع عميق (يحل الأخطاء الإملائية)
    normalized_input = deep_normalize(user_input)

    # 2. جرب dictionary match
    match_result = dict_match(normalized_input)
    intent       = match_result["intent"]
    confidence   = match_result.get("confidence", 0.0)

    # 3. إذا unclear → جرب النص الأصلي (تطابق دقيق له أولوية)
    if intent == Intent.UNCLEAR:
        match_result2 = dict_match(user_input)
        if match_result2["intent"] != Intent.UNCLEAR:
            intent     = match_result2["intent"]
            confidence = match_result2.get("confidence", 0.0)

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
        from lab_v4_dev.intent.llm_intent_resolver import resolve
        intent     = resolve(user_input)
        confidence = 0.8

    # 7.5 — Natural dialogue fallback.
    # Reuse PERSONAL_CHAT for inputs that remain UNCLEAR only when
    # they contain no explicit operational/system/project signal.
    if intent == Intent.UNCLEAR:
        _chat_norm = normalize(user_input).strip()
        _operational_signals = (
            "ملف", "مجلد", "مشروع", "نظام", "كود", "الكود",
            "تنفيذ", "نفذ", "شغل", "تشغيل", "اعرض", "اظهر",
            "ابحث", "حلل", "قارن", "عدّل", "تعديل", "احذف",
            "امسح", "نظف", "تنظيف", "اختبر", "اختبار",
            "تقرير", "حالة", "مهمة", "مهام", "جلسة",
            "استكمل", "استكمال", "استرجع", "استعادة",
            "project", "file", "code", "run", "test"
        )
        if _chat_norm and not any(
            _token_has_word(_chat_norm, signal)
            for signal in _operational_signals
        ):
            intent = Intent.PERSONAL_CHAT
            confidence = 0.60

    # HELP remains unsupported here when no dedicated help route won.
    if intent == Intent.HELP:
        intent = Intent.UNSUPPORTED

    # 8. استخراج الهدف
    # PHASE-2 COMPATIBILITY:
    # Historical routing contract requires the direct question
    # "ما حالة النظام" to resolve to STATUS.
    #
    # Do not globally collapse SYSTEM_STATUS into STATUS because
    # SYSTEM_STATUS is a distinct orchestrator capability.
    _status_question = normalize(user_input) in {
        "ما حالة النظام",
        "ما حاله النظام",
    }
    if _status_question and intent == Intent.SYSTEM_STATUS:
        intent = Intent.STATUS

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
            # token-aware check using unicode word boundaries
            return _token_has_word(_txt_norm, w)

        # If explicit device token present, promote to CLEAN_DEVICE
        if any(_has_word(w) for w in device_indicators):
            intent = Intent.CLEAN_DEVICE

        # If explicit code/project token present, promote to CLEANUP_CODE only when cleaning signal present
        clean_indicators = ["نظف", "تنظيف", "نظفه", "نظّف", "مسح", "إزالة", "تفريغ", "clean", "clear"]
        if intent != Intent.CLEAN_DEVICE and any(_has_word(w) for w in code_indicators):
            if intent == Intent.CLEAN or any(_token_has_word(_txt_norm, c) for c in clean_indicators):
                intent = Intent.CLEANUP_CODE

        # If resolved intent is generic CLEAN but no explicit device/code target — treat as unsupported (ambiguous)
        if intent == Intent.CLEAN:
            # If target or explicit device indicator present, keep; otherwise demote to unsupported
            explicit_device = any(_has_word(w) for w in device_indicators)
            explicit_code   = any(_has_word(w) for w in code_indicators)
            if not explicit_device and not explicit_code and not target:
                intent = Intent.UNSUPPORTED
    except Exception:
        pass

    # DNI-10: resolve command pronouns only from context explicitly granted
    # by the conversation layer; never pull an unrelated global NLU entity.
    if not target and user_input.strip() in ("احذفه", "احذفها", "احذفها"):
        try:
            last = context_entity if isinstance(context_entity, dict) else {}
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
    # PHASE-2 DELETE AUTHORITY:
    # An explicit delete-file request with a concrete file target
    # must never be downgraded/reinterpreted by later context
    # routing.
    _explicit_delete = any(
        _token_has_word(_txt_norm, w)
        for w in (
            "احذف",
            "احذف الملف",
            "حذف",
            "امسح الملف",
            "ازالة الملف",
            "إزالة الملف",
        )
    )

    if _explicit_delete and target:
        intent = Intent.DELETE_FILE

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
        "entity_type": entity_type,
        "semantic_pattern": semantic_pattern,
    }


def parse(user_input, *, context_entity: dict | None = None):
    """
    Canonical public intent entrypoint.

    The historical semantic implementation is preserved privately in
    _interpret(). This adapter exposes the unified IntentResult contract
    without changing the underlying semantic precedence.
    """
    if isinstance(user_input, IntentResult):
        result = user_input
        result.validate()
        return result

    if not isinstance(user_input, str):
        raise TypeError("intent parser input must be a string")

    legacy = _interpret(user_input, context_entity=context_entity)

    if isinstance(legacy, IntentResult):
        legacy.validate()
        return legacy

    if not isinstance(legacy, dict):
        raise TypeError(
            f"intent parser returned unsupported type: {type(legacy).__name__}"
        )

    legacy = dict(legacy)
    signal = classify_conversation_semantics(
        user_input,
        intent=legacy.get("intent"),
        target=legacy.get("target", ""),
        entity_type=legacy.get("entity_type", ""),
    )
    legacy.setdefault(
        "conversation_domain",
        signal.get("conversation_domain", "general"),
    )
    legacy.setdefault("conversation_act", signal.get("conversation_act", "NONE"))
    legacy.setdefault(
        "conversation_confidence",
        float(signal.get("confidence", 0.0)),
    )
    legacy.setdefault(
        "response_attributes",
        dict(signal.get("response_attributes") or {}),
    )

    result = IntentResult(
        intent=legacy.get("intent"),
        confidence=float(legacy.get("confidence", 0.0)),
        target=legacy.get("target"),
        action=legacy.get("action"),
        context=legacy.get("context"),
        raw=legacy.get("raw", user_input),
        entity_type=legacy.get("entity_type", ""),
        semantic_pattern=legacy.get("semantic_pattern", ""),
        context_inherited=legacy.get("context_inherited", False),
        conversation_domain=legacy.get("conversation_domain", "general"),
        conversation_act=legacy.get("conversation_act", "NONE"),
        conversation_confidence=legacy.get("conversation_confidence", 0.0),
        response_attributes=legacy.get("response_attributes", {}),
    )

    result.validate()
    return result
