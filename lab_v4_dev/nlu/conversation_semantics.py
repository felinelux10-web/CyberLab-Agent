"""Lightweight semantic signals for non-executable conversation turns.

This module classifies conversational function, not executable intent. It uses
normalized token-level cues and grammatical context instead of sentence-sized
phrase inventories. Canonical intent resolution and execution ownership remain
with IntentParser and ConversationManager.
"""
from __future__ import annotations

import re
import unicodedata


# Short concept vocabularies are deliberately kept at the semantic-marker level.
_GREETING_MARKERS = {"سلام", "مرحبا", "اهلا", "هلا", "صباح", "مساء", "تحيه"}
_ACK_MARKERS = {
    "شكر", "اشكر", "مشكور", "ممتن", "يعطيك", "عافيه", "تسلم", "سلمت",
    "قصرت", "ممتاز", "جميل",
}
_CLOSING_MARKERS = {
    "وداع", "لقاء", "تصبح", "اراك", "اشوف", "امان", "باي", "لاحقا",
}
_STATE_MARKERS = {
    "حال", "شعور", "تحس", "اخبار", "امور", "يوم", "اطمن", "طمن", "طمني", "بخير", "كيفك",
}
_CAPABILITY_MARKERS = {"تقدر", "تستطيع", "قادر", "قدره", "مساعد", "تساعد"}
_IDENTITY_MARKERS = {
    "اسم", "شخص", "هويه", "طبيعه", "ماهيه", "وظيفه", "تعريف", "نفس",
    "حضرتك", "yourself", "identity",
}
_AGENT_REFERENCE_MARKERS = {"وكيل", "مساعد", "agent", "assistant", "cyberlab"}
_AGENT_ARCHITECTURE_MARKERS = {
    "بنيه", "معماريه", "طبقه", "طبقات", "مكون", "مكونات", "وحده", "وحدات",
    "architecture", "layers", "modules", "components", "structure", "gateway",
    "orchestrator", "نظام", "system",
}
_AGENT_FLOW_MARKERS = {
    "رساله", "رسالت", "request", "input", "تعالج", "معالجه", "تستقبل", "تمر",
    "مسار", "flow", "يحدث", "يصير", "ادخال", "ظهور", "رد", "تتعامل", "تعامل",
    "تجاوب", "تجيب", "ترد", "تنتقل", "تبدأ", "تنتهي", "تسير", "تشتغل",
    "يدخل", "تدخل", "تنفيذ", "عمليه", "يعمل", "تعمل", "process", "handle",
    "respond", "answer", "works",
}
_AGENT_LIMIT_MARKERS = {
    "حد", "حدود", "قيود", "limitations", "limitation", "cannot", "impossible",
    "مستحيل", "يتعذر",
}
_AGENT_GROUNDING_MARKERS = {
    "مصدر", "مأخوذ", "مبني", "مستند", "موثق", "مثبت", "تستند", "تعتمد",
    "grounded", "source", "based",
}
_AGENT_CAPABILITY_MARKERS = {
    "تقدر", "تستطيع", "قادر", "قدره", "مساعد", "تساعد", "وظيفه",
    "وظائف", "امكانيات", "قدرات", "تفعل", "تسوي", "يسوي",
    "capability", "capabilities", "capable",
}
_AGENT_SECOND_PERSON_VERBS = {
    "تستطيع", "تقدر", "تستخدم", "تستعمل", "تعالج", "تتعامل",
    "تقول", "تصف", "تعرف", "تشرح", "تجاوب", "تجيب", "ترد", "تسوي",
    "تملك", "تمتلك", "تستند", "تعتمد", "تحلل", "تفهم", "تنفذ",
    "بتقدر", "بتستخدم", "بتتعامل", "you", "your", "yourself",
}
_AGENT_PROJECT_SUBJECT_MARKERS = {
    "مشروع", "project", "ملف", "ملفات", "file", "files", "مجلد", "مجلدات",
    "folder", "folders", "كود", "code", "repository", "repo",
}
_AGENT_FILE_OPERATION_MARKERS = {
    "حلل", "تحليل", "افحص", "فحص", "راجع", "مراجعة", "اشرح", "وضح",
    "analyze", "inspect", "review", "explain", "read", "open", "modify",
    "edit", "run", "execute", "test", "اقرا", "افتح", "عدل", "شغل",
    "تشغل", "نفذ", "اختبر",
}
_AGENT_QUERY_ACTS = {
    "agent_identity": "ASSISTANT_IDENTITY_QUERY",
    "agent_capabilities": "ASSISTANT_CAPABILITY_QUERY",
    "agent_architecture": "AGENT_ARCHITECTURE_QUERY",
    "agent_execution_flow": "AGENT_EXECUTION_FLOW_QUERY",
    "agent_limits": "AGENT_LIMITS_QUERY",
}
_AGENT_QUERY_INTENTS = frozenset(_AGENT_QUERY_ACTS)
_INTERPERSONAL_MARKERS = {
    "احب", "اشتاق", "وجود", "صديق", "صحبه", "لطيف", "محادثه", "حديث",
}
_OPENING_MARKERS = {"ندردش", "نحكي", "نتحدث", "نتكلم", "نسولف", "سوالف"}
_OPINION_MARKERS = {"راي", "وجهه", "نظرك"}

_SIMPLIFY_MARKERS = {"بسط", "ابسط", "مبسط", "مبسطه", "بسيط", "اسهل", "اسهلها"}
_CONCISE_MARKERS = {"اختصر", "مختصر", "موجز", "اقصر", "اقل"}
_DETAILED_MARKERS = {"مفصل", "مفصلا", "تفصيلا", "تفصيل"}
_ACADEMIC_MARKERS = {"اكاديمي", "علمي", "اكاديميه"}
_FORMAL_MARKERS = {"فصحى", "رسمي", "رسميه", "فصيح"}
_COLLOQUIAL_MARKERS = {"عامي", "عاميه", "لهجه", "دارجه"}
_WARM_TONE_MARKERS = {"ودي", "ودود", "لطيف", "وديه"}
_RESPONSE_REFERENCES = {
    "شرح", "كلام", "رد", "جواب", "اجابه", "صياغه", "اسلوب", "نبره",
    "هذا", "هذه", "ذلك", "تلك",
    "خاطب", "تحدث", "تكلم", "معي",
}
_CORRECTION_MARKERS = {"اقصد", "اقصده", "المقصود", "تصحيح", "صحح"}
_CORRECTION_NEGATIONS = {"لا", "ليس", "مو", "مش", "غلط"}
_COMPOUND_REFERENCE_MARKERS = {
    "هذا", "هذه", "ذلك", "تلك", "جزء", "نقطه", "شرح", "موضوع", "السابق",
}
_RETURN_MARKERS = {"ارجع", "عوده", "رجوع", "الرئيسي", "الرئيسيه"}
_QUESTION_MARKERS = {"هل", "ما", "ماذا", "كيف", "من", "مين", "ايش", "شو", "بماذا"}
_WORKING_MARKERS = {"يعمل", "تعمل", "يشتغل", "تشتغل", "works", "working"}
_PROJECT_MARKERS = {
    "مشروع", "ملف", "مجلد", "كود", "الكود", "برمجه", "وحده", "مكون",
    "داله", "سطر", "تصميم", "معماريه", "بنيه", "وكيل", "cyberlab",
    "orchestrator", "gateway", "python", "javascript",
}
_TECHNICAL_MARKERS = {
    "sql", "injection", "csrf", "xss", "ثغره", "امان", "امني", "سيبراني",
    "هجوم", "اختراق", "بروتوكول", "api", "database", "backend", "frontend",
}
_SYSTEM_MARKERS = {"نظام", "النظام", "تشغيل", "حاله النظام"}

# Intent classes that can be conversational/semantic rather than an explicit
# executable operation. Other canonical intents retain their original authority.
_NON_EXECUTABLE_INTENTS = {
    "", "unclear", "unknown", "unsupported", "help", "personal_chat",
    "status", "system_status", "cyber_explain", "context_report",
    "work_context", "question", "discussion", "chat",
    *_AGENT_QUERY_INTENTS,
}
_SOCIAL_ACTS = {
    "SOCIAL_GREETING", "SOCIAL_ACKNOWLEDGEMENT", "SOCIAL_CLOSING",
    "SOCIAL_OPENING", "ASSISTANT_STATE_QUERY", "ASSISTANT_CAPABILITY_QUERY",
    "ASSISTANT_IDENTITY_QUERY", "PERSONAL_INTERACTION", "CASUAL_DISCUSSION",
    "SOCIAL_FOLLOW_UP", "CASUAL_CONVERSATION",
}
_STYLE_ACTS = {
    "SIMPLIFICATION_REQUEST", "VERBOSITY_REQUEST", "FORMALITY_REQUEST",
    "TONE_REQUEST", "STYLE_REQUEST",
}


_ARABIC_CHARACTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ء": "",
    "ؤ": "و", "ئ": "ي", "ى": "ي", "ة": "ه",
    "ک": "ك", "ڪ": "ك", "ی": "ي", "ے": "ي",
})
_ARABIC_CLITIC_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك")
_ARABIC_PRONOUN_SUFFIXES = ("هما", "كما", "كم", "كن", "هن", "هم", "ها", "نا", "ني", "ه", "ك", "ي")


def normalize_text(text: str) -> str:
    """Normalize Unicode Arabic, optional marks, and punctuation as boundaries."""
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = value.translate(_ARABIC_CHARACTER_MAP)
    chars = []
    for char in value:
        category = unicodedata.category(char)
        if char == "ـ" or category.startswith("M") or category == "Cf":
            continue
        chars.append(" " if category.startswith("P") else char)
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def _tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    return re.findall(
        r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+|[a-z0-9_]+",
        normalized,
    )


def _agent_bases(tokens: list[str]) -> set[str]:
    """Expose common Arabic clitic/possessive forms without sentence matching."""
    bases = set(tokens)
    for token in tokens:
        prefix_forms = {token}
        candidate = token
        for _ in range(3):
            prefix = next(
                (
                    item for item in _ARABIC_CLITIC_PREFIXES
                    if candidate.startswith(item) and len(candidate) > len(item) + 1
                ),
                None,
            )
            if not prefix:
                break
            candidate = candidate[len(prefix):]
            prefix_forms.add(candidate)
        bases.update(prefix_forms)
        for form in prefix_forms:
            for suffix in _ARABIC_PRONOUN_SUFFIXES:
                if form.endswith(suffix) and len(form) > len(suffix) + 1:
                    bases.add(form[:-len(suffix)])
    return bases


def _one_edit_apart(left: str, right: str) -> bool:
    """Allow one insertion, deletion, substitution, or adjacent transposition."""
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        mismatches = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        if len(mismatches) <= 1:
            return True
        if len(mismatches) == 2:
            i, j = mismatches
            return j == i + 1 and left[i] == right[j] and left[j] == right[i]
        return False

    longer, shorter = (left, right) if len(left) > len(right) else (right, left)
    i = j = edits = 0
    while i < len(longer) and j < len(shorter):
        if longer[i] == shorter[j]:
            i += 1
            j += 1
        else:
            edits += 1
            i += 1
            if edits > 1:
                return False
    return True


def _has_agent_any(
    bases: set[str], markers: set[str], *, same_initial_for_fuzzy: bool = True
) -> bool:
    """Match semantic tokens exactly, morphologically, or with one safe typo."""
    normalized_markers = {normalize_text(marker) for marker in markers}
    for raw_token in bases:
        token = normalize_text(raw_token).replace(" ", "")
        if token in normalized_markers:
            return True
        if any(len(marker) >= 4 and token.startswith(marker) for marker in normalized_markers):
            return True
        for marker in normalized_markers:
            if len(marker) < 4 or not _one_edit_apart(token, marker):
                continue
            if same_initial_for_fuzzy and token[:1] != marker[:1]:
                continue
            return True
    return False


def _has_file_operation_target(text: str, bases: set[str]) -> bool:
    has_file_target = bool(
        re.search(r"(?<!\w)[\w./-]+\.[\w]{1,12}(?!\w)", text, flags=re.UNICODE)
    )
    return has_file_target and _has_agent_any(bases, _AGENT_FILE_OPERATION_MARKERS)


def _has_direct_agent_reference(tokens: list[str], bases: set[str]) -> bool:
    explicit = {
        "انت", "انتي", "انتو", "انتم", "حضرتك", "منك", "لك", "معك", "عليك",
        "اليك", "فيك", "عندك", "you", "your", "yourself",
    }
    if bases & explicit:
        return True
    if any(
        token.endswith(("كم", "كن", "ك")) and len(token) >= 3
        for token in tokens
        if token not in {"يمكن", "لكن", "ملك"}
    ):
        return True

    nominal_subjects = (
        _AGENT_ARCHITECTURE_MARKERS
        | _AGENT_REFERENCE_MARKERS
        | _AGENT_PROJECT_SUBJECT_MARKERS
        | _TECHNICAL_MARKERS
    )
    for index, token in enumerate(tokens):
        if not _has_agent_any(
            _agent_bases([token]),
            _AGENT_SECOND_PERSON_VERBS,
            same_initial_for_fuzzy=True,
        ):
            continue
        adjacent = tokens[max(0, index - 1):index] + tokens[index + 1:index + 2]
        if any(_has_agent_any(_agent_bases([word]), nominal_subjects) for word in adjacent):
            continue
        return True
    return False


def _has_negated_capability(tokens: list[str]) -> bool:
    """Detect negation attached to an ability predicate, not elsewhere in text."""
    modals = {"تستطيع", "تقدر", "قادر", "يمكنك", "capable", "can"}
    negators = {"لا", "ليس", "لن", "لم", "مش", "مو", "غير", "cannot", "not", "never"}
    for index, token in enumerate(tokens):
        token_forms = _agent_bases([token])
        if not _has_agent_any(token_forms, modals, same_initial_for_fuzzy=True):
            continue
        previous = tokens[max(0, index - 2):index]
        if any(
            _has_agent_any(_agent_bases([word]), negators)
            for word in previous
        ):
            return True
    return False


def _bases(tokens: list[str]) -> set[str]:
    bases = set(tokens)
    for token in tokens:
        candidate = token
        # Remove common conjunction/preposition/article clitics for matching
        # concept markers (e.g. السلام, وبالمساعدة, وأخبارك).
        for prefix in ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك"):
            if candidate.startswith(prefix) and len(candidate) > len(prefix) + 1:
                candidate = candidate[len(prefix):]
                break
        bases.add(candidate)
        # Arabic second-person suffixes are useful for assistant-directed
        # questions and do not require enumerating complete utterances.
        # Exclude modal "يمكن", which happens to end with the same letters.
        if (
            candidate != "يمكن"
            and candidate.endswith(("ك", "كم", "كن"))
            and len(candidate) > 3
        ):
            bases.add(candidate[:-1])
            if candidate.endswith(("كم", "كن")):
                bases.add(candidate[:-2])
    return bases


def _has_any(bases: set[str], markers: set[str]) -> bool:
    normalized_markers = {
        normalize_text(marker).replace(" ", "") for marker in markers
    }
    if bases & normalized_markers:
        return True
    return any(
        any(token.startswith(marker) for marker in normalized_markers if len(marker) >= 4)
        for token in bases
    )


def _has_second_person(tokens: list[str], bases: set[str]) -> bool:
    explicit = {"انت", "انتي", "انتو", "انتم", "حضرتك", "منك", "لك", "معك", "عليك", "اليك"}
    if bases & explicit:
        return True
    # "يمكن" is a modal verb, not a second-person suffix form.
    return any(
        token != "يمكن"
        and token.endswith(("ك", "كم", "كن"))
        and len(token) > 3
        for token in tokens
    )


def _has_explicit_second_person(tokens: list[str], bases: set[str]) -> bool:
    pronouns = {"انت", "انتي", "انتو", "انتم", "حضرتك", "منك", "لك", "معك", "عليك", "اليك"}
    return bool(bases & pronouns)


def classify_agent_self_query(text: str) -> dict | None:
    """Classify agent-self requests from meaning, not punctuation or syntax.

    A self reference, a first-person message-processing frame, or an
    unambiguous property of the named agent is required. Merely mentioning the
    project/agent beside an architecture word does not make a project question
    an agent-self query.
    """
    raw = str(text or "").strip()
    tokens = _tokens(raw)
    if not tokens:
        return None
    bases = _bases(tokens) | _agent_bases(tokens)
    if _has_file_operation_target(raw, bases):
        return None
    project_subject = _has_agent_any(bases, _AGENT_PROJECT_SUBJECT_MARKERS)
    direct_address = _has_direct_agent_reference(tokens, bases)
    agent_reference = _has_agent_any(bases, _AGENT_REFERENCE_MARKERS)
    message_frame = (
        _has_agent_any(bases, {
            "رساله", "رسالت", "message", "request", "input", "سؤال", "question",
        })
        and _has_agent_any(bases, _AGENT_FLOW_MARKERS)
    )

    # Explicit project framing wins unless the wording actually relates the
    # user to the agent (e.g. "معالجة رسالتي" or "الطبقات التي تستخدمها أنت").
    if project_subject and not (direct_address or message_frame):
        return None

    identity = _has_agent_any(bases, _IDENTITY_MARKERS)
    capability = _has_agent_any(bases, _AGENT_CAPABILITY_MARKERS)
    architecture = _has_agent_any(bases, _AGENT_ARCHITECTURE_MARKERS)
    flow = _has_agent_any(bases, _AGENT_FLOW_MARKERS)
    limits = _has_agent_any(bases, _AGENT_LIMIT_MARKERS)
    grounding = _has_agent_any(bases, _AGENT_GROUNDING_MARKERS)
    negated_capability = _has_negated_capability(tokens)

    # A named agent may be asked about its role/capabilities without a pronoun;
    # architecture alone is not enough, because that commonly means project
    # structure (e.g. "مكونات CyberLab Agent").
    named_agent_property = agent_reference and (
        identity
        or capability
        or limits
        or (flow and _has_agent_any(bases, _WORKING_MARKERS))
    )
    if not (direct_address or message_frame or named_agent_property):
        return None

    if limits or (grounding and (direct_address or message_frame)) or negated_capability:
        intent = "agent_limits"
    elif identity or (
        bool(tokens) and tokens[0] in {"من", "مين", "who"}
        and (direct_address or agent_reference)
    ):
        intent = "agent_identity"
    elif architecture and (direct_address or message_frame):
        intent = "agent_architecture"
    elif flow and message_frame:
        intent = "agent_execution_flow"
    elif agent_reference and _has_agent_any(bases, _WORKING_MARKERS):
        intent = "agent_execution_flow"
    elif capability:
        intent = "agent_capabilities"
    elif flow and (direct_address or named_agent_property):
        intent = "agent_execution_flow"
    else:
        return None

    return {
        "conversation_domain": "agent_self",
        "conversation_act": _AGENT_QUERY_ACTS[intent],
        "confidence": 0.92,
        "response_attributes": {},
        "conversational": True,
        "intent": intent,
    }


def _domain(text: str, bases: set[str], target: str = "", entity_type: str = "") -> str:
    if _has_any(bases, _SYSTEM_MARKERS):
        return "system"
    if entity_type.upper() in {"FILE", "COMPONENT"} or _has_any(bases, _PROJECT_MARKERS):
        return "project"
    if entity_type.upper() == "CONCEPT" or _has_any(bases, _TECHNICAL_MARKERS):
        return "technical"
    if target and (
        "." in target or "/" in target or target.startswith(("/", "~/"))
    ):
        return "project"
    return "social"


def classify_conversation_semantics(
    text: str,
    *,
    intent=None,
    target: str = "",
    entity_type: str = "",
) -> dict:
    """Return semantic act/domain/style signals without choosing a route."""
    raw = str(text or "").strip()
    tokens = _tokens(raw)
    bases = _bases(tokens)
    intent_value = getattr(intent, "value", intent)
    intent_value = str(intent_value or "").casefold()
    domain = _domain(raw, bases, str(target or ""), str(entity_type or ""))

    if intent_value in _AGENT_QUERY_INTENTS:
        return {
            "conversation_domain": "agent_self",
            "conversation_act": _AGENT_QUERY_ACTS[intent_value],
            "confidence": 0.94,
            "response_attributes": {},
            "conversational": True,
        }

    agent_signal = classify_agent_self_query(raw)
    if agent_signal and intent_value in _NON_EXECUTABLE_INTENTS:
        return agent_signal

    # An explicit canonical operation is not demoted by a friendly word or
    # response-style cue embedded in its wording.
    if intent_value and intent_value not in _NON_EXECUTABLE_INTENTS:
        return {
            "conversation_domain": "execution",
            "conversation_act": "EXECUTABLE_REQUEST",
            "confidence": 1.0,
            "response_attributes": {},
            "conversational": False,
        }

    has_response_reference = _has_any(bases, _RESPONSE_REFERENCES)
    attrs = {}
    has_correction = (
        _has_any(bases, _CORRECTION_MARKERS)
        and _has_any(bases, _CORRECTION_NEGATIONS | {"بل"})
    )
    has_compound_reference = (
        len(tokens) >= 2
        and _has_any(bases, {"نقطه", "جزء", "موضوع"})
        and _has_any(bases, _COMPOUND_REFERENCE_MARKERS)
    )
    if has_correction:
        return {
            "conversation_domain": "general",
            "conversation_act": "CORRECTION",
            "confidence": 0.92,
            "response_attributes": {},
            "conversational": True,
        }
    if _has_any(bases, _RETURN_MARKERS) and _has_any(
        bases, {"موضوع", "الرئيسي", "السابق"}
    ):
        return {
            "conversation_domain": "general",
            "conversation_act": "TOPIC_RETURN",
            "confidence": 0.90,
            "response_attributes": {},
            "conversational": True,
        }
    if has_response_reference:
        if _has_any(bases, _SIMPLIFY_MARKERS):
            attrs["interaction_style"] = "simplified"
        if _has_any(bases, _CONCISE_MARKERS):
            attrs["verbosity"] = "concise"
        elif _has_any(bases, _DETAILED_MARKERS):
            attrs["verbosity"] = "detailed"
        if _has_any(bases, _ACADEMIC_MARKERS):
            attrs["formality"] = "academic"
        elif _has_any(bases, _FORMAL_MARKERS):
            attrs["formality"] = "formal"
        elif _has_any(bases, _COLLOQUIAL_MARKERS):
            attrs["formality"] = "colloquial"
        if _has_any(bases, _WARM_TONE_MARKERS):
            attrs["tone"] = "warm"

    if attrs:
        if "interaction_style" in attrs:
            act = "SIMPLIFICATION_REQUEST"
        elif "verbosity" in attrs:
            act = "VERBOSITY_REQUEST"
        elif "formality" in attrs:
            act = "FORMALITY_REQUEST"
        else:
            act = "TONE_REQUEST"
        return {
            "conversation_domain": "style",
            "conversation_act": act,
            "confidence": 0.92,
            "response_attributes": attrs,
            "conversational": True,
        }

    if has_compound_reference:
        return {
            "conversation_domain": "general",
            "conversation_act": "COMPOUND_REFERENCE",
            "confidence": 0.86,
            "response_attributes": {},
            "conversational": True,
        }

    # Project/technical entities and operations take precedence over social
    # readings of broad question or opinion markers.
    domain_specific = domain in {"project", "technical", "system"}
    second_person = _has_second_person(tokens, bases)
    if not domain_specific:
        if (
            _has_any(bases, _WORKING_MARKERS)
            and (
                tokens[0] in _QUESTION_MARKERS
                or "؟" in raw
                or "?" in raw
            )
        ):
            act = "TOPIC_CONTINUATION_QUERY"
        elif _has_any(bases, _GREETING_MARKERS):
            act = "SOCIAL_GREETING"
        elif _has_any(bases, _ACK_MARKERS):
            act = "SOCIAL_ACKNOWLEDGEMENT"
        elif _has_any(bases, _CLOSING_MARKERS):
            act = "SOCIAL_CLOSING"
        elif _has_any(bases, _OPENING_MARKERS):
            act = "SOCIAL_OPENING"
        elif _has_any(bases, _STATE_MARKERS) and (
            second_person
            or "كيفك" in bases
            # This short Arabic greeting omits the second-person suffix.
            or (
                len(tokens) == 2
                and tokens[0] == "كيف"
                and _has_any(bases, {"حال"})
            )
        ):
            act = "ASSISTANT_STATE_QUERY"
        elif _has_any(bases, _CAPABILITY_MARKERS) and (
            second_person or _has_any(bases, {"تقدر", "تستطيع", "يمكن", "قادر"})
        ):
            act = "ASSISTANT_CAPABILITY_QUERY"
        elif (
            _has_any(bases, {"يمكن"})
            and second_person
            and len(tokens) <= 4
            and tokens[0] in {"ما", "ماذا", "هل", "ايش", "شو"}
        ):
            act = "ASSISTANT_CAPABILITY_QUERY"
        elif (
            _has_any(bases, _IDENTITY_MARKERS)
            or (bool(tokens) and tokens[0] in {"من", "مين"} and second_person)
        ) and (second_person or "مين" in bases):
            act = "ASSISTANT_IDENTITY_QUERY"
        elif _has_any(bases, _INTERPERSONAL_MARKERS) and second_person:
            act = "PERSONAL_INTERACTION"
        elif (
            len(tokens) <= 4
            and _has_explicit_second_person(tokens, bases)
            and ("؟" in raw or "?" in raw or _has_any(bases, _QUESTION_MARKERS))
        ):
            act = "SOCIAL_FOLLOW_UP"
        elif _has_any(bases, _OPINION_MARKERS) and len(tokens) > 2:
            act = "CASUAL_DISCUSSION"
        else:
            act = None

        if act:
            return {
                "conversation_domain": "social",
                "conversation_act": act,
                "confidence": 0.88,
                "response_attributes": {},
                "conversational": True,
            }

    # The canonical parser already chose the non-executable conversational
    # route; use a general act rather than inventing a more specific one.
    if intent_value == "personal_chat":
        return {
            "conversation_domain": "social" if not domain_specific else domain,
            "conversation_act": "CASUAL_CONVERSATION",
            "confidence": 0.60,
            "response_attributes": {},
            "conversational": True,
        }

    return {
        "conversation_domain": domain if domain_specific else "general",
        "conversation_act": "NONE",
        "confidence": 0.0,
        "response_attributes": {},
        "conversational": False,
    }


def should_override_with_personal_chat(text: str, signal: dict, *, mode: str, target: str = "") -> bool:
    """Whether a strong conversational act should replace a weak semantic hit."""
    if mode in {"TASK", "SYSTEM"} or target:
        return False
    if not signal.get("conversational"):
        return False
    bases = _bases(_tokens(text))
    if _domain(str(text), bases, target) in {"project", "technical", "system"}:
        return False
    act = signal.get("conversation_act")
    return act in (_SOCIAL_ACTS | _STYLE_ACTS | {"TOPIC_CONTINUATION_QUERY"})


def is_style_act(act: str | None) -> bool:
    return str(act or "").upper() in _STYLE_ACTS


def is_social_act(act: str | None) -> bool:
    return str(act or "").upper() in _SOCIAL_ACTS
