"""Lightweight semantic signals for non-executable conversation turns.

This module classifies conversational function, not executable intent. It uses
normalized token-level cues and grammatical context instead of sentence-sized
phrase inventories. Canonical intent resolution and execution ownership remain
with IntentParser and ConversationManager.
"""
from __future__ import annotations

import re


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
    "اسم", "شخص", "هويه", "طبيعه", "وظيفه", "تعريف", "نفس", "حضرتك",
}
_AGENT_REFERENCE_MARKERS = {"وكيل", "agent", "cyberlab"}
_AGENT_ARCHITECTURE_MARKERS = {
    "بنيه", "معماريه", "طبقه", "طبقات", "مكون", "مكونات", "وحده", "وحدات",
    "architecture", "layers", "modules", "gateway", "orchestrator", "نظام", "system",
}
_AGENT_FLOW_MARKERS = {
    "رساله", "رسالت", "request", "input", "تعالج", "معالجه", "تستقبل", "تمر",
    "مسار", "flow", "يحدث", "ادخال", "ظهور", "رد",
}
_AGENT_LIMIT_MARKERS = {"حد", "حدود", "قيود", "limitations", "limitation", "cannot"}
_AGENT_CAPABILITY_MARKERS = {
    "تقدر", "تستطيع", "قادر", "قدره", "مساعد", "تساعد", "وظيفه",
    "وظائف", "امكانيات", "قدرات", "تفعل", "capability", "capabilities",
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


def normalize_text(text: str) -> str:
    value = str(text or "").casefold()
    value = re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670\u0640]", "", value)
    value = re.sub(r"[أإآٱ]", "ا", value).replace("ى", "ي").replace("ة", "ه")
    return value


def _tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    normalized = re.sub(r"[؟?!.،,؛:…()\[\]{}\"'«»]", " ", normalized)
    return re.findall(r"[\u0600-\u06FF]+|[a-z0-9_]+", normalized)


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
    """Classify a question about this agent from compact semantic cues.

    The classifier requires a question shape plus an agent-directed subject,
    an agent reference, or a message-processing frame. An explicit project
    subject wins over an incidental mention of the agent name.
    """
    raw = str(text or "").strip()
    tokens = _tokens(raw)
    if not tokens:
        return None
    bases = _bases(tokens)
    question = (
        "؟" in raw
        or "?" in raw
        or tokens[0] in _QUESTION_MARKERS
    )
    if not question:
        return None

    project_subject = _has_any(bases, {"مشروع", "project", "ملف", "مجلد", "كود", "repository"})
    direct_address = _has_second_person(tokens, bases) or _has_any(
        bases, {"تستطيع", "تقدر", "يمكنك"}
    )
    agent_reference = _has_any(bases, _AGENT_REFERENCE_MARKERS)
    message_frame = (
        _has_any(bases, {"رساله", "رسالت", "request", "input"})
        and _has_any(bases, _AGENT_FLOW_MARKERS)
    )

    if project_subject and not direct_address:
        return None
    if not (direct_address or agent_reference or message_frame):
        return None

    capability = _has_any(bases, _AGENT_CAPABILITY_MARKERS)
    negated_capability = capability and _has_any(
        bases, {"لا", "ليس", "cannot", "غير قادر"}
    ) and _has_any(bases, {"تستطيع", "تقدر", "قادر", "يمكنك", "تنفيذ", "تفعل"})

    if _has_any(bases, _AGENT_LIMIT_MARKERS) or negated_capability:
        intent = "agent_limits"
    elif _has_any(bases, _IDENTITY_MARKERS) or (
        tokens[0] in {"من", "مين"} and _has_second_person(tokens, bases)
    ):
        intent = "agent_identity"
    elif capability:
        intent = "agent_capabilities"
    elif _has_any(bases, _AGENT_ARCHITECTURE_MARKERS):
        intent = "agent_architecture"
    elif _has_any(bases, _AGENT_FLOW_MARKERS) and (
        direct_address or message_frame or agent_reference
    ):
        intent = "agent_execution_flow"
    elif agent_reference and _has_any(bases, {"يعمل", "تعمل", "يشتغل", "تشتغل"}):
        intent = "agent_execution_flow"
    else:
        return None

    return {
        "conversation_domain": "agent_self",
        "conversation_act": _AGENT_QUERY_ACTS[intent],
        "confidence": 0.94,
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
