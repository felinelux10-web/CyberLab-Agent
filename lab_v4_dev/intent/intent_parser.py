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
    classify_agent_self_query,
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
    def _clean(value: str) -> str:
        return value.strip().strip(".,،؛:!?؟()[]{}\"'")
    # أولاً: مسار كامل يبدأ بـ ~/ أو /
    m = re.search(r"(?:^|\s)([~/][\w./_~-]+\.\w+)", text)
    if m:
        return _clean(m.group(1))
    # ثانياً: مسار نسبي أو اسم ملف
    m = re.search(r"(?<![؀-ۿ])([\w][\w./:-]*\.\w+)", text)
    if m:
        return _clean(m.group(0))
    # ثالثاً: بعد كلمة ملف/file
    m = re.search(r"(?:ملف|file)\s+(\S+)", text)
    if m:
        value = _clean(m.group(1))
        return value if "." in value or "/" in value or "\\" in value else ""
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


# Cleanup is executable only when an action verb is present. Target nouns
# classify that action; they never create a cleanup intent on their own.
_CLEAN_ACTION_SUFFIXES = {
    "نظف": ("", "ه", "ها", "ي", "وا"),
    "تنظيف": ("",),
    "مسح": ("", "ه", "ها", "ي", "وا"),
    "امسح": ("", "ه", "ها", "ي", "وا"),
    "تفريغ": ("",),
    "ازاله": ("",),
    "clean": ("",),
    "clear": ("",),
}
_DELETE_ACTION_SUFFIXES = {
    "احذف": ("", "ه", "ها", "هم", "ي", "وا"),
    "حذف": ("", "ه", "ها"),
    "امسح": ("", "ه", "ها", "ي", "وا"),
    "ازاله": ("",),
}
_READ_ACTION_SUFFIXES = {
    "اقرا": ("", "ه", "ها", "ني"),
    "قرا": ("", "ه", "ها"),
    "افتح": ("", "ه", "ها", "ي", "وا"),
    "اعرض": ("", "ه", "ها", "ي", "وا"),
    "read": ("",),
    "open": ("",),
    "show": ("",),
}
_CODE_ANALYSIS_ACTION_SUFFIXES = {
    "حلل": ("", "ه", "ها", "ي", "وا"),
    "افحص": ("", "ه", "ها", "ي", "وا"),
    "راجع": ("", "ه", "ها", "ي", "وا"),
    "analyze": ("",),
    "inspect": ("",),
    "review": ("",),
}
_RUN_TEST_ACTION_SUFFIXES = {
    "شغل": ("", "ها", "هم", "ي", "وا"),
    "تشغل": ("", "ها", "هم", "ي", "وا"),
    "نفذ": ("", "ها", "هم", "وا"),
    "run": ("",),
    "execute": ("",),
}
_ACTION_QUERY_OPENERS = {
    "هل", "ما", "ماذا", "كيف", "لماذا", "ليش", "من", "مين", "ايش", "شو",
    "what", "why", "how", "who", "where", "when", "can", "could", "would",
}
_INFORMATION_QUERY_OPENERS = _ACTION_QUERY_OPENERS - {"هل", "can", "could", "would"}
_CAPABILITY_REQUEST_MARKERS = {"يمكنك", "تستطيع", "تقدر", "ممكن"}
_ANALYSIS_NOMINAL_ACTIONS = {"تحليل", "فحص", "مراجعة"}
_TEST_NOMINAL_ACTIONS = {"تشغيل", "تنفيذ"}
_TEST_TARGET_STEMS = ("اختبار", "اختبارات", "test", "tests")
_DEVICE_TARGET_STEMS = (
    "هاتف", "جهاز", "جوال", "موبايل", "phone", "device", "mobile",
)
_CODE_TARGET_STEMS = (
    "كود", "مشروع", "ملف", "مجلد", "code", "project", "file", "folder",
)
_CLEAN_NEGATORS = ("لا", "لن", "لم", "ليس", "مش", "مو")
_ARABIC_TOKEN_PREFIXES = (
    "وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك",
)
_ARABIC_TOKEN_SUFFIXES = (
    "هما", "كما", "كم", "كن", "هن", "هم", "ها", "ه", "نا", "ني", "ي", "وا",
)


def _token_prefix_forms(token: str) -> set[str]:
    """Strip only recognized Arabic clitics; never infer a stem by prefix."""
    forms = {token}
    candidate = token
    for _ in range(3):
        prefix = next(
            (
                item
                for item in _ARABIC_TOKEN_PREFIXES
                if candidate.startswith(item)
                and len(candidate) > len(item) + 1
            ),
            None,
        )
        if not prefix:
            break
        candidate = candidate[len(prefix):]
        forms.add(candidate)
    return forms


def _has_stem_token(text: str, stems: tuple[str, ...]) -> bool:
    """Match a whole lexical token with limited Arabic suffix/clitic forms."""
    normalized = normalize(text).casefold()
    tokens = re.findall(r"[\w]+", normalized, flags=re.UNICODE)
    stem_set = {stem.casefold() for stem in stems}
    for token in tokens:
        for candidate in _token_prefix_forms(token):
            if candidate in stem_set:
                return True
            if candidate.endswith("s") and candidate[:-1] in stem_set:
                return True
            if any(
                candidate.endswith(suffix)
                and candidate[:-len(suffix)] in stem_set
                for suffix in _ARABIC_TOKEN_SUFFIXES
            ):
                return True
    return False


def _has_lexical_action(
    text: str,
    action_suffixes: dict[str, tuple[str, ...]],
) -> bool:
    tokens = re.findall(r"[\w]+", normalize(text).casefold(), flags=re.UNICODE)
    action_forms = {
        stem + suffix
        for stem, suffixes in action_suffixes.items()
        for suffix in suffixes
    }
    for index, token in enumerate(tokens):
        if not any(form in action_forms for form in _token_prefix_forms(token)):
            continue
        preceding = tokens[max(0, index - 2):index]
        if any(_has_stem_token(word, _CLEAN_NEGATORS) for word in preceding):
            continue
        return True
    return False


def _has_cleanup_action(text: str) -> bool:
    return _has_lexical_action(text, _CLEAN_ACTION_SUFFIXES)


def _has_delete_action(text: str) -> bool:
    return _has_lexical_action(text, _DELETE_ACTION_SUFFIXES)


def _has_read_action(text: str) -> bool:
    return _has_lexical_action(text, _READ_ACTION_SUFFIXES)


def _is_action_target_request(
    text: str,
    action_suffixes: dict[str, tuple[str, ...]],
    target_stems: tuple[str, ...],
    nominal_actions: set[str],
) -> bool:
    """Resolve an action with its target without executing interrogative mentions."""
    if target_stems and not _has_stem_token(text, target_stems):
        return False

    has_verb_action = _has_lexical_action(text, action_suffixes)
    has_nominal_action = _has_stem_token(text, nominal_actions)
    tokens = re.findall(r"[\w]+", normalize(text).casefold(), flags=re.UNICODE)
    if not tokens:
        return False

    opener = tokens[0]
    if opener in _INFORMATION_QUERY_OPENERS:
        return False
    if opener == "هل":
        return (
            _has_stem_token(text, _CAPABILITY_REQUEST_MARKERS)
            and (has_verb_action or has_nominal_action)
        )
    if opener in {"can", "could", "would"}:
        directed_to_user = len(tokens) > 1 and tokens[1] in {"you", "we"}
        return directed_to_user and (has_verb_action or has_nominal_action)
    return has_verb_action


def _resolve_cleanup_intent(text: str, candidate: str) -> str:
    """Resolve cleanup as action + target, never by target mention alone."""
    has_action = _has_cleanup_action(text)
    has_device_target = _has_stem_token(text, _DEVICE_TARGET_STEMS)
    has_code_target = _has_stem_token(text, _CODE_TARGET_STEMS) or bool(
        _extract_target(text)
    )

    if not has_action:
        # A fuzzy/prefix-only action guess is ambiguous, not executable.
        if candidate in {Intent.CLEAN, Intent.CLEAN_DEVICE, Intent.CLEANUP_CODE}:
            return Intent.UNCLEAR
        if candidate == Intent.DELETE_FILE and not _has_delete_action(text):
            return Intent.UNCLEAR
        if candidate == Intent.READ_FILE and not _has_read_action(text):
            return Intent.UNCLEAR
        return candidate

    # Explicit project/code/file targets outrank a device mention when both
    # appear in one request (e.g. "clean the project on my phone").
    if has_code_target:
        return Intent.CLEANUP_CODE
    if has_device_target:
        return Intent.CLEAN_DEVICE
    return Intent.CLEAN


def _device_memory_request_kind(text: str) -> str | None:
    """Separate live device-memory checks from requests to explain memory."""
    normalized = normalize(text).casefold()
    deep = deep_normalize(text).casefold()
    tokens = re.findall(r"[\w]+", f"{normalized} {deep}", flags=re.UNICODE)
    token_set = set(tokens)
    memory_terms = {
        "ram", "رام", "الرام", "ذاكرة", "الذاكرة", "ذاكره", "الذاكره",
        "memory",
    }
    if not token_set.intersection(memory_terms):
        return None

    # Explicit educational framing stays on the general explanation path.
    explanation_terms = {
        "اشرح", "شرح", "وضح", "توضيح", "فسر", "تفسير", "معنى", "معني",
        "فرق", "الفرق", "explain", "explanation", "difference", "definition",
    }
    if token_set.intersection(explanation_terms):
        return "knowledge"
    if len(tokens) >= 2 and tokens[0] in {"ما", "ماذا", "what"} and tokens[1] in {
        "هي", "هو", "الفرق", "فرق", "معنى", "معني", "meaning",
    }:
        return "knowledge"

    device_terms = {
        "هاتف", "الهاتف", "هاتفي", "جهاز", "الجهاز", "جهازي", "جوال",
        "الجوال", "phone", "mobile", "device", "android", "ios",
    }
    measurement_terms = {
        "كم", "حجم", "مقدار", "عندي", "لدي", "استهلاك", "استخدام",
        "مستخدم", "متاح", "usage", "used", "total", "available", "free",
    }
    explicit_ram = {"ram", "رام", "الرام"}
    if (
        token_set.intersection(device_terms | measurement_terms)
        or (len(tokens) <= 2 and token_set.intersection(explicit_ram))
    ):
        return "unsupported"
    return None


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
        "TOPIC_CONTINUATION_QUERY",
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


_AGENT_ACT_INTENTS = {
    "ASSISTANT_IDENTITY_QUERY": Intent.AGENT_IDENTITY,
    "ASSISTANT_CAPABILITY_QUERY": Intent.AGENT_CAPABILITIES,
    "AGENT_ARCHITECTURE_QUERY": Intent.AGENT_ARCHITECTURE,
    "AGENT_EXECUTION_FLOW_QUERY": Intent.AGENT_EXECUTION_FLOW,
    "AGENT_LIMITS_QUERY": Intent.AGENT_LIMITS,
}


def _agent_self_result(user_input: str) -> dict | None:
    signal = classify_agent_self_query(user_input)
    if not signal:
        return None
    intent = _AGENT_ACT_INTENTS.get(signal.get("conversation_act"))
    if not intent:
        return None
    return {
        "intent": intent,
        "target": "",
        "context": "general",
        "confidence": float(signal.get("confidence", 0.94)),
        "raw": user_input,
        "source": "agent_self_semantics",
        "entity_type": "AGENT_SELF",
        "semantic_pattern": str(signal.get("conversation_act", "")),
        "conversation_domain": "agent_self",
        "conversation_act": signal.get("conversation_act", "NONE"),
        "conversation_confidence": float(signal.get("confidence", 0.94)),
        "response_attributes": {},
    }


def _project_architecture_intent(user_input: str):
    """Resolve project/component structure questions by subject and concept."""
    text = normalize(user_input).casefold()
    tokens = set(re.findall(r"[\w]+", text, flags=re.UNICODE))
    bases = set(tokens)
    for token in tokens:
        for prefix in ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل"):
            if token.startswith(prefix) and len(token) > len(prefix) + 1:
                bases.add(token[len(prefix):])
                break

    question = (
        "؟" in user_input
        or "?" in user_input
        or bool(bases & {"ما", "ماذا", "كيف", "هل", "اشرح", "وضح", "حدثني"})
    )
    if not question:
        return None

    architecture_markers = {
        "بنيه", "هيكل", "معماريه", "طبقه", "طبقات", "مكون", "مكونات",
        "وحده", "وحدات", "architecture", "layers", "modules", "components",
    }
    work_markers = {
        "يعمل", "تعمل", "يشتغل", "تشتغل", "معالجه", "تعالج", "process", "flow",
    }
    project_markers = {"مشروع", "project", "المشروع", "repository"}
    component_markers = {
        "gateway", "orchestrator", "module", "component", "طبقه", "مكون",
        "وحده", "نظام", "system",
    }

    has_architecture = bool(bases & architecture_markers)
    has_work = bool(bases & work_markers)
    asks_how = "كيف" in bases
    if has_architecture and bool(bases & project_markers):
        return Intent.PROJECT_SCAN
    if has_architecture and bool(bases & component_markers):
        return Intent.ARCHITECTURE
    if has_work and asks_how and bool(bases & component_markers):
        return Intent.ARCHITECTURE
    return None


def _has_project_request_evidence(user_input: str) -> bool:
    """Require a project operation/question, not the noun's mere presence."""
    text = normalize(user_input).casefold()
    tokens = set(re.findall(r"[\w]+", text, flags=re.UNICODE))
    project_words = {"مشروع", "المشروع", "project", "repository", "cyberlab"}
    if not tokens & project_words:
        return True
    evidence = {
        "افحص", "فحص", "حلل", "تحليل", "اعرض", "اقرا", "اقرأ", "اشرح",
        "خريطة", "هيكل", "بنية", "مكونات", "طبقات", "ملفات", "عدد",
        "تقدم", "وصلنا", "انجزنا", "نظرة", "حالة", "الحالي", "النشط",
        "اخر", "آخر", "اشتغل", "اشتغلت", "عمل", "عملت", "عملنا",
        "where", "what", "how", "show", "read", "analyze", "scan",
    }
    return bool(tokens & evidence)


def _project_mention_without_request(user_input: str) -> bool:
    text = normalize(user_input).casefold()
    tokens = set(re.findall(r"[\w]+", text, flags=re.UNICODE))
    return bool(tokens & {"مشروع", "المشروع", "project", "repository", "cyberlab"}) and not _has_project_request_evidence(user_input)


def _project_history_intent(user_input: str):
    """Resolve project-history questions from grammatical roles, not phrases."""
    text = normalize(user_input).casefold()
    tokens = set(re.findall(r"[\w]+", text, flags=re.UNICODE))
    project_terms = {"مشروع", "المشروع", "مشاريع", "المشاريع", "project", "projects"}
    work_terms = {"اشتغل", "اشتغلت", "اشتغلنا", "عمل", "عملت", "عملنا", "يعمل", "يشتغل"}
    if not (tokens & project_terms and tokens & work_terms):
        return None
    if tokens & {"مشاريع", "المشاريع", "projects"}:
        return Intent.PROJECT_INDEX
    if tokens & {"اخر", "آخر", "السابق", "سابق"}:
        return Intent.LAST_PROJECT
    return Intent.PROJECT_INDEX



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

    agent_self_result = _agent_self_result(user_input)
    if agent_self_result is not None:
        return agent_self_result

    # Dialogue-history references are not operational HISTORY requests.
    # Keep them conversational so ConversationManager can resolve them from
    # DialogueMemory rather than from task/project history.
    normalized_raw = normalize(user_input).casefold()
    if any(marker in normalized_raw for marker in (
        "الحوار السابق", "النقاش السابق", "الحديث السابق", "محادثتنا السابقة",
    )):
        return {
            "intent": Intent.PERSONAL_CHAT,
            "target": "",
            "context": "general",
            "confidence": 0.92,
            "raw": user_input,
            "source": "dialogue_reference",
            "entity_type": "REFERENCE",
            "conversation_act": "TOPIC_RETURN",
            "conversation_domain": "general",
            "conversation_confidence": 0.92,
        }

    if re.search(r"الفرق بين سؤال عام.*تحليل ملف|سؤال عام.*ملف محدد", raw):
        return {
            "intent": Intent.PERSONAL_CHAT,
            "target": "",
            "context": "general",
            "confidence": 0.93,
            "raw": user_input,
            "source": "meta_question",
            "entity_type": "CONVERSATION",
        }

    project_history_intent = _project_history_intent(user_input)
    if project_history_intent is not None:
        return {
            "intent": project_history_intent,
            "target": "",
            "context": "project_level",
            "confidence": 0.93,
            "raw": user_input,
            "source": "project_history_semantics",
            "entity_type": "PROJECT",
            "semantic_pattern": "PROJECT_HISTORY_QUERY",
        }

    # A project noun inside a social/meta sentence is not a project command.
    # Require explicit project evidence before allowing PROJECT_SCAN below.
    if _project_mention_without_request(user_input):
        return {
            "intent": Intent.PERSONAL_CHAT,
            "target": "",
            "context": "general",
            "confidence": 0.86,
            "raw": user_input,
            "source": "ambiguous_project_mention",
            "entity_type": "CONVERSATION",
        }

    # Project component questions are conversational knowledge requests, not
    # file-operation targets. Keep the target empty so later NLU fallback
    # cannot turn the remainder of the sentence into a pseudo-file target.
    _component_names = (
        "conversationmanager", "conversation_manager", "orchestrator",
        "intentparser", "intent_parser", "eventloop", "event_loop",
    )
    _component_text = normalize(user_input).casefold().replace(" ", "")
    _component_question = any(name in _component_text for name in _component_names)
    _component_project_words = ("مشروع", "cyberlab", "بنية", "مكون", "دور", "فرق", "علاقة")
    if _component_question and any(word in normalize(user_input) for word in _component_project_words):
        if re.search(r"ما الفرق|الفرق بين|قارن|مقارنة", raw):
            return {
                "intent": Intent.ARCHITECTURE,
                "target": "",
                "context": "project_level",
                "confidence": 0.94,
                "raw": user_input,
                "source": "project_component_comparison",
                "entity_type": "COMPONENT",
            }
        return {
            "intent": Intent.CYBER_EXPLAIN,
            "target": "",
            "context": "project_level",
            "confidence": 0.94,
            "raw": user_input,
            "source": "project_component_question",
            "entity_type": "COMPONENT",
        }

    if _is_action_target_request(
        user_input,
        _RUN_TEST_ACTION_SUFFIXES,
        _TEST_TARGET_STEMS,
        _TEST_NOMINAL_ACTIONS,
    ):
        return {
            "intent": Intent.RUN_TESTS,
            "target": "",
            "context": detect_context(user_input),
            "confidence": 0.94,
            "raw": user_input,
            "source": "executable_action_target",
            "entity_type": "PROJECT",
            "semantic_pattern": "TEST_RUN_ACTION",
        }

    analysis_target = _extract_target(user_input)
    if analysis_target and _is_action_target_request(
        user_input,
        _CODE_ANALYSIS_ACTION_SUFFIXES,
        (),
        _ANALYSIS_NOMINAL_ACTIONS,
    ):
        return {
            "intent": Intent.ANALYZE_CODE,
            "target": analysis_target,
            "context": detect_context(user_input),
            "confidence": 0.94,
            "raw": user_input,
            "source": "executable_action_target",
            "entity_type": "FILE",
            "semantic_pattern": "CODE_ANALYSIS_ACTION",
        }

    project_architecture_intent = _project_architecture_intent(user_input)
    if project_architecture_intent is not None:
        return {
            "intent": project_architecture_intent,
            "target": "",
            "context": "project_level",
            "confidence": 0.91,
            "raw": user_input,
            "source": "project_architecture_semantics",
            "entity_type": "COMPONENT",
            "semantic_pattern": "PROJECT_ARCHITECTURE_QUERY",
        }

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
                    # Keep explicit delete resolution separate from cleanup
                    # action/target classification below.
                    _txt_norm = normalize(user_input)

                    def _has_word(w):
                        try:
                            pattern = r"(?<!\w)" + re.escape(w) + r"(?!\w)"
                            return bool(re.search(pattern, _txt_norm, flags=re.UNICODE))
                        except re.error:
                            return w in _txt_norm

                    chosen_intent = nlu_result["intent"]
                    chosen_conf   = nlu_result.get("confidence", 0.0)

                    # if NLU says a delete action but there's an explicit file target -> DELETE_FILE
                    if re.search(r"\bاحذ?ف\b", _txt_norm) and (any(_has_word(w) for w in FILE_INDICATORS) or _extract_target(user_input)):
                        chosen_intent = Intent.DELETE_FILE

                chosen_intent = _resolve_cleanup_intent(user_input, chosen_intent)

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

    memory_request = _device_memory_request_kind(user_input)
    if memory_request == "unsupported":
        return {
            "intent": Intent.UNSUPPORTED,
            "target": "",
            "context": detect_context(user_input),
            "confidence": 0.95,
            "raw": user_input,
            "entity_type": "UNKNOWN",
            "semantic_pattern": "DEVICE_MEMORY_UNSUPPORTED",
        }
    if memory_request == "knowledge":
        return {
            "intent": Intent.PERSONAL_CHAT,
            "target": "",
            "context": detect_context(user_input),
            "confidence": 0.90,
            "raw": user_input,
            "entity_type": "CONCEPT",
            "semantic_pattern": "DEVICE_MEMORY_KNOWLEDGE",
        }

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
    _txt_norm = normalize(user_input)
    intent = _resolve_cleanup_intent(user_input, intent)

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
    _explicit_delete = _has_delete_action(user_input)

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
