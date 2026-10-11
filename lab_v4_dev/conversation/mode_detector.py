"""Conversation shape detector.

This module classifies the broad form of a turn. Canonical executable intent
belongs to IntentParser; unknown natural language is not an implicit task.
"""
import re

from lab_v4_dev.nlu.entity_extractor import extract
from lab_v4_dev.nlu.conversation_semantics import normalize_text


# These remain a narrow set of explicit operational/system action cues. They
# are not intended to enumerate the user's natural-language vocabulary.
TASK_PATTERNS = [
    "افحص", "اقرأ", "اكتب", "حلل", "شغّل", "شغل", "نفذ", "احذف",
    "انشئ", "أنشئ", "عدل", "اعرض", "ابحث", "احفظ الجلسة", "خريطة",
    "تاثير", "اعتماديات", "خطورة",
]

SYSTEM_PATTERNS = [
    "استكمل الجلسة", "احفظ الجلسة", "امسح الحوار",
    "أعد التشغيل", "اعد التشغيل", "اعرض آخر جلسة",
    "ما اخر جلسة", "ما آخر جلسة", "حالة النظام",
    "كيف حال النظام", "وضع النظام",
]

_QUESTION_WORDS = {
    "هل", "كيف", "ما", "ماذا", "من", "مين", "اين", "متى", "كم",
    "اي", "ايش", "شو", "لماذا", "بماذا",
}
_DISCUSSION_MARKERS = {
    "راي", "نناقش", "ناقش", "الفرق", "افضل", "ايهما", "مقارنة", "بدائل",
}
_FOLLOW_UP_PREFIXES = ("ولماذا", "وماذا", "وما علاقته", "ماذا عن", "ما علاقته")
_FOLLOW_UP_ROLE_MARKERS = {"دوره", "دورها", "وظيفته", "وظيفتها", "علاقته", "علاقتها"}
_EXPLANATION_STARTS = ("اشرح", "وضح", "عرفني", "بين لي", "حدثني")


def _tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    normalized = re.sub(r"[؟?!.،,؛:…()\[\]{}\"'«»]", " ", normalized)
    return re.findall(r"[\u0600-\u06FF]+|[a-z0-9_]+", normalized)


def _token_bases(tokens: list[str]) -> set[str]:
    bases = set(tokens)
    for token in tokens:
        for prefix in ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل"):
            if token.startswith(prefix) and len(token) > len(prefix) + 1:
                bases.add(token[len(prefix):])
                break
        if token.endswith("ك") and len(token) > 3:
            bases.add(token[:-1])
    return bases


def _is_short_follow_up(text: str, tokens: list[str]) -> bool:
    if not tokens or len(tokens) > 7:
        return False

    # EntityExtractor owns the generic pronoun/reference marker vocabulary.
    try:
        entity_type = str(extract(text, "").get("type", "")).upper()
        if entity_type in {"REFERENCE", "ELABORATION"}:
            return True
    except Exception:
        pass

    normalized = normalize_text(text).strip(" \t\r\n؟?!.،,؛:")
    if any(normalized.startswith(prefix) for prefix in _FOLLOW_UP_PREFIXES):
        return True

    if any(token in _FOLLOW_UP_ROLE_MARKERS for token in tokens):
        return True

    # Short elliptical process questions generally refer to the prior subject;
    # an explicit object (file, project, or named subject) remains a QUESTION.
    explicit_subject = any(
        token in {"النظام", "المشروع", "الملف", "الوكيل", "الكود"}
        or "." in token
        or "/" in token
        for token in tokens
    )
    if not explicit_subject and len(tokens) <= 3:
        if "كيف" in tokens and any(token.startswith("يعمل") or token.startswith("تعمل") for token in tokens):
            return True
        if "لماذا" in tokens:
            return True
    return False


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = normalize_text(text).casefold()
    normalized_phrase = normalize_text(phrase).casefold().strip()
    if not normalized_phrase:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(
        re.escape(part) for part in normalized_phrase.split()
    ) + r"(?!\w)"
    return re.search(pattern, normalized, flags=re.UNICODE) is not None


def _is_lexical_mention(text: str) -> bool:
    tokens = _tokens(text)
    bases = _token_bases(tokens)
    if not bases & {
        "كلمه", "الكلمه", "مصطلح", "المصطلح", "عباره", "العباره",
        "لفظ", "اللفظ", "معنى", "المعنى",
    }:
        return False
    first = tokens[0] if tokens else ""
    return first not in {
        "احذف", "امسح", "نظف", "افحص", "حلل", "اعرض", "اقرا", "اقرأ",
        "اكتب", "عدل", "شغل", "نفذ", "انشئ", "افتح", "ابحث", "قارن",
    }


def _has_explicit_task_request(text: str) -> bool:
    tokens = _tokens(text)
    if not tokens:
        return False
    normalized = normalize_text(text).casefold().strip()
    action_forms = tuple(TASK_PATTERNS)
    first = tokens[0]
    if any(_contains_phrase(first, action) for action in action_forms):
        return True

    # Common politeness/request prefixes may precede the actual imperative.
    request_prefixes = (
        "لو سمحت", "من فضلك", "رجاء", "يرجى", "أريد", "اريد",
        "قم", "please", "i want", "i need",
    )
    if any(normalized.startswith(normalize_text(prefix).casefold()) for prefix in request_prefixes):
        prefix_tokens = tokens[:5]
        return any(
            _contains_phrase(" ".join(prefix_tokens), action)
            for action in action_forms
        )
    return False


def detect_mode(text: str) -> str:
    """Return TASK, SYSTEM, DISCUSSION, QUESTION, FOLLOW_UP, or CHAT."""
    raw = str(text or "").strip()
    if not raw:
        return "CHAT"

    # Mentioning an action word is not itself a request to execute it.
    if _is_lexical_mention(raw):
        tokens = _tokens(raw)
        if "؟" in raw or "?" in raw or (tokens and tokens[0] in _QUESTION_WORDS):
            return "QUESTION"
        return "CHAT"

    # Explicit system controls must lead the request (or follow a
    # recognized request prefix); an incidental phrase is not a system command.
    system_prefixes = ("لو سمحت", "من فضلك", "رجاء", "يرجى", "please")
    normalized_raw = normalize_text(raw).casefold()
    if any(_contains_phrase(raw, pattern) for pattern in SYSTEM_PATTERNS) and (
        any(normalized_raw.startswith(normalize_text(prefix).casefold()) for prefix in system_prefixes)
        or any(
            normalized_raw.startswith(normalize_text(pattern).casefold())
            for pattern in SYSTEM_PATTERNS
        )
    ):
        return "SYSTEM"

    # Only an imperative/request frame makes an operational cue TASK.
    if _has_explicit_task_request(raw):
        return "TASK"

    tokens = _tokens(raw)
    if _is_short_follow_up(raw, tokens):
        return "FOLLOW_UP"

    normalized = normalize_text(raw)
    bases = _token_bases(tokens)
    if (
        ("راي" in bases and len(tokens) > 2)
        or any(marker in bases for marker in _DISCUSSION_MARKERS - {"راي"})
    ):
        return "DISCUSSION"

    first = tokens[0] if tokens else ""
    if (
        "؟" in raw
        or "?" in raw
        or first in _QUESTION_WORDS
        or normalized.startswith(_EXPLANATION_STARTS)
    ):
        return "QUESTION"

    # CHAT is the safe descriptive default. IntentParser still recognizes and
    # routes an explicit executable request even if its wording is unusual.
    return "CHAT"
