"""Unified bounded local responder for offline conversational turns.

The engine consumes the canonical parse, semantic request, and authorized
conversation history. It does not execute operations or invent factual history.
It returns None when a turn needs general knowledge or unsupported free-form
generation, allowing the existing provider route to remain authoritative.
"""
from __future__ import annotations

import re
from typing import Any

from lab_v4_dev.nlu.conversation_semantics import normalize_text


_LOCAL_ACTS = {
    "SOCIAL_GREETING",
    "SOCIAL_ACKNOWLEDGEMENT",
    "SOCIAL_CLOSING",
    "ASSISTANT_STATE_QUERY",
    "SOCIAL_OPENING",
    "CASUAL_CONVERSATION",
    "CASUAL_DISCUSSION",
    "SOCIAL_FOLLOW_UP",
    "PERSONAL_INTERACTION",
    "CONVERSATION_CONTINUATION",
    "TOPIC_CONTINUATION_QUERY",
    "TOPIC_RETURN",
}


def _clean(value: Any, limit: int = 260) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _history_parts(history: list | None) -> tuple[str, str]:
    """Return the last user and assistant turns from already-authorized history."""
    user_text = ""
    assistant_text = ""
    for turn in reversed(history or []):
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").casefold()
        content = _clean(turn.get("content"), 420)
        if not content:
            continue
        if role == "assistant" and not assistant_text:
            assistant_text = content
        elif role == "user" and not user_text:
            user_text = content
        if user_text and assistant_text:
            break
    return user_text, assistant_text


def _topic(parsed: dict, semantic: dict, history: list | None) -> str:
    target = _clean(parsed.get("target") or semantic.get("target"), 100)
    if target:
        return target
    for turn in reversed(history or []):
        if not isinstance(turn, dict):
            continue
        kind = str(turn.get("context_kind") or "").casefold()
        domain = str(turn.get("conversation_domain") or "").casefold()
        if kind in {"work", "system", "execution", "project"} or domain in {
            "work", "system", "execution", "project",
        }:
            continue
        target = _clean(turn.get("target"), 100)
        if target:
            return target
    return ""


def _result(text: str, parsed: dict, source: str = "local_unified_response") -> dict:
    return {
        "status": "success",
        "intent": parsed.get("intent") or "personal_chat",
        "text": text,
        "mode": "CHAT",
        "source": source,
        "executed": False,
        "local_strategy": "semantic_context_composition",
    }


def answer_local_response(
    text: str,
    parsed: dict | None = None,
    semantic_request: dict | None = None,
    *,
    history: list | None = None,
    context_entity: dict | None = None,
) -> dict | None:
    """Compose a context-aware local reply for bounded conversational acts."""
    parsed = parsed if isinstance(parsed, dict) else {}
    semantic = semantic_request if isinstance(semantic_request, dict) else {}
    act = str(
        parsed.get("conversation_act")
        or semantic.get("conversation_act")
        or ""
    ).strip().upper()
    intent = str(getattr(parsed.get("intent"), "value", parsed.get("intent")) or "").casefold()
    domain = str(
        parsed.get("conversation_domain")
        or semantic.get("conversation_domain")
        or "general"
    ).casefold()
    if act not in _LOCAL_ACTS:
        return None
    if domain in {"work", "system", "execution", "project"} or intent in {
        "run_tests", "run_project", "run_script", "modify_file", "modify_code",
        "delete_file", "save_kb", "session_restore", "work_status", "work_context",
    }:
        return None

    normalized = normalize_text(text).strip()
    if not normalized:
        return None
    last_user, last_assistant = _history_parts(history)
    topic = _topic(parsed, semantic, history)
    if isinstance(context_entity, dict) and not topic:
        topic = _clean(context_entity.get("entity"), 100)

    if act == "SOCIAL_GREETING":
        # Keep the active subject available when history was explicitly granted;
        # do not claim a new topic or replace it with a generic greeting.
        if topic and last_user:
            reply = (
                f"أهلًا بك. ما زال لدينا سياق سابق حول «{topic}». "
                "هل تفضّل استكماله أم بدء موضوع مختلف؟"
            )
        elif any(word in normalized.split() for word in ("صباح", "مساء")):
            reply = "أهلًا بك. هل ترغب في حديث خفيف أم لديك موضوع محدد تريد مناقشته؟"
        else:
            reply = "أهلًا بك. يمكننا متابعة موضوع سابق أو فتح موضوع جديد؛ ما الأنسب لك الآن؟"
        return _result(reply, parsed, "local_social_engine")

    if act == "SOCIAL_CLOSING":
        reply = (
            f"حسنًا، نتوقف هنا عند موضوع «{topic}». يمكنك العودة إليه لاحقًا."
            if topic else
            "حسنًا، نتوقف هنا. يمكنك العودة إلى الحوار متى أردت."
        )
        return _result(reply, parsed, "local_social_engine")

    if act == "SOCIAL_ACKNOWLEDGEMENT":
        if any(word in normalized.split() for word in ("شكرا", "اشكرك", "ممتن", "مشكور")):
            reply = "على الرحب والسعة. يمكننا متابعة النقطة السابقة أو الانتقال إلى مسألة أخرى."
        elif last_assistant and any(mark in last_assistant for mark in ("؟", "?", "اختر", "ما رأيك", "ما رأيك")):
            reply = (
                "فهمت موافقتك. سأتابع من السؤال السابق"
                + (f" حول «{topic}»." if topic else ".")
                + " إذا كنت تقصد مسارًا آخر فصحّح لي."
            )
        elif last_user and topic:
            reply = f"حسنًا، يمكننا البناء على حديثنا عن «{topic}». أي جانب تريد تناوله أولًا؟"
        else:
            reply = "حسنًا. حدّد ما تريد متابعته، أو اذكر موضوعًا جديدًا."
        return _result(reply, parsed, "local_social_engine")

    if act == "ASSISTANT_STATE_QUERY":
        if any(word in normalized.split() for word in ("اليوم", "الان", "الآن", "اخبار", "أخبار")) and topic:
            reply = f"يمكننا اليوم متابعة «{topic}»، أو اختيار موضوع جديد. هل تريد الاستمرار في السياق السابق؟"
        else:
            reply = "أنا جاهز لمناقشة طلبك. هل تريد حديثًا عامًا، أم سؤالًا محددًا، أم متابعة موضوع سابق؟"
        return _result(reply, parsed, "local_social_engine")

    if act in {"CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY", "TOPIC_RETURN"}:
        if not last_user and not last_assistant and not topic:
            return _result(
                "لا أجد في السياق المتاح نقطة سابقة موثوقة أتابع منها. اذكر الموضوع أو أرسل جزءًا من الحوار المقصود.",
                parsed,
            )
        anchor = topic or _clean(last_user, 100)
        if last_user and last_assistant:
            reply = (
                f"نستأنف الحوار من «{anchor}». آخر ما طرحته كان: «{last_user}». "
                f"وكان الرد السابق: «{last_assistant}». "
                "يمكنني الآن توضيح هذه النقطة أو متابعة الجانب الذي لم نناقشه بعد؛ أيهما تقصد؟"
            )
        elif last_user:
            reply = (
                f"أستطيع المتابعة من رسالتك السابقة: «{last_user}». "
                "لا يظهر في السياق رد سابق كافٍ لبناء استكمال أدق؛ ما الجانب الذي تريد توسيعه؟"
            )
        else:
            reply = f"الموضوع الذي أمكن استعادته هو «{anchor}»، لكن لا توجد تفاصيل كافية عن آخر نقطة. ما الجانب الذي تريد متابعته؟"
        return _result(reply, parsed)

    if act in {"SOCIAL_OPENING", "CASUAL_CONVERSATION", "CASUAL_DISCUSSION", "PERSONAL_INTERACTION"}:
        if topic and last_user:
            reply = (
                f"يمكننا مواصلة الحديث عن «{topic}» بصورة غير رسمية. "
                f"آخر نقطة طرحتها كانت «{last_user}». ما الذي لفت انتباهك فيها؟"
            )
        else:
            reply = (
                "يمكننا البدء من فكرة بسيطة ثم تطوير النقاش بحسب ما يهمك. "
                "هل تفضّل موضوعًا عن الفن، أو الأفكار والحياة اليومية، أو التقنية؟"
            )
        return _result(reply, parsed)

    if act == "SOCIAL_FOLLOW_UP":
        if any(marker in normalized for marker in ("اقترح", "اقتراح", "ماذا تقترح", "ما تقترح")):
            if topic and last_user:
                reply = (
                    f"أقترح أن نتابع «{topic}» من زاوية جديدة مرتبطة بما ذكرتَه: "
                    f"«{last_user}». يمكننا فحص الأسباب أولًا، ثم مقارنة وجهتي نظر مختلفتين."
                )
            else:
                reply = (
                    "يمكننا اختيار موضوع يتيح نقاشًا متدرجًا: كيف يؤثر الفن في فهمنا للعالم، "
                    "أو كيف تتشكل العادات والقرارات، أو أين ينبغي أن تتوقف التقنية عن اتخاذ القرار نيابة عن الإنسان. "
                    "أي اتجاه أقرب إلى اهتمامك؟"
                )
            return _result(reply, parsed)
        if topic and last_user:
            return _result(
                f"بالنظر إلى حديثنا عن «{topic}»، يمكن أن تكون الخطوة التالية فحص الفكرة التي ذكرتها «{last_user}» من زاوية أخرى. ما الجانب الذي تريد التركيز عليه؟",
                parsed,
            )

    # Unknown/open factual questions must not be answered with invented content.
    return None
