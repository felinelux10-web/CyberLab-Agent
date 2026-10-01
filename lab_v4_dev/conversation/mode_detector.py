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


def detect_mode(text: str) -> str:
    """Return TASK, SYSTEM, DISCUSSION, QUESTION, FOLLOW_UP, or CHAT."""
    raw = str(text or "").strip()
    if not raw:
        return "CHAT"

    # Explicit system controls precede generic action/question shape.
    if any(pattern in raw for pattern in SYSTEM_PATTERNS):
        return "SYSTEM"

    # Preserve explicit operational verbs; intent remains authoritative for
    # whether an operation actually executes.
    if any(pattern in raw for pattern in TASK_PATTERNS):
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
