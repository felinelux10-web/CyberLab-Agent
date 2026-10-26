"""Evidence-free but bounded local responses for high-confidence social acts.

This is deliberately not a local knowledge model. It handles only conversational
acts that do not require factual retrieval or free-form generation. Knowledge
questions, project questions, contextual continuations, and operational requests
must remain owned by their existing specialized routes.
"""
from __future__ import annotations

from lab_v4_dev.nlu.conversation_semantics import is_social_act, normalize_text


_ALLOWED_ACTS = {
    "SOCIAL_GREETING",
    "SOCIAL_ACKNOWLEDGEMENT",
    "SOCIAL_CLOSING",
    "ASSISTANT_STATE_QUERY",
}


def answer_local_social(text: str, parsed: dict | None = None) -> dict | None:
    """Answer only bounded social acts; open-ended dialogue remains with the conversational responder."""
    parsed = parsed if isinstance(parsed, dict) else {}
    act = str(parsed.get("conversation_act") or "").strip().upper()
    if act not in _ALLOWED_ACTS or not is_social_act(act):
        return None

    normalized = normalize_text(text)
    if not normalized:
        return None

    # Keep the response language formal Arabic and avoid claiming human feelings.
    if act == "SOCIAL_GREETING":
        reply = "مرحبًا بك. ما الموضوع الذي تود التحدث عنه؟"
    elif act == "SOCIAL_ACKNOWLEDGEMENT":
        if any(token in normalized.split() for token in ("شكرا", "اشكرك", "ممتن", "مشكور")):
            reply = "على الرحب والسعة. هل تريد متابعة الموضوع أم الانتقال إلى موضوع آخر؟"
        else:
            reply = "حسنًا. يمكننا المتابعة من النقطة التي تختارها."
    elif act == "SOCIAL_CLOSING":
        reply = "إلى اللقاء. يمكنك العودة إلى الحوار متى أردت."
    elif act == "ASSISTANT_STATE_QUERY":
        reply = "أنا جاهز لمساعدتك. ما الذي تود العمل عليه أو مناقشته؟"
    else:
        reply = (
            "يمكننا إجراء حوار عادي دون تحويله إلى مهمة تقنية. "
            "اختر موضوعًا يهمك، أو اذكر ما يشغل بالك، وسأتابع معك."
        )

    return {
        "status": "success",
        "intent": parsed.get("intent") or "personal_chat",
        "text": reply,
        "mode": "CHAT",
        "source": "local_social_engine",
        "executed": False,
    }
