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
    "CONVERSATION_HISTORY_QUERY",
}


def _clean(value: Any, limit: int = 260) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


_SOCIAL_RESET_TURNS = {
    normalize_text(value)
    for value in (
        "اهلا", "اهلا بك", "اهلا وسهلا", "مرحبا", "السلام عليكم",
        "صباح الخير", "مساء الخير", "لنتحدث قليلا", "نتحدث قليلا",
        "دعنا نتحدث", "نريد ان نتحدث فقط", "دردشة فقط",
    )
}
_SOCIAL_ASSISTANT_PREFIXES = tuple(
    normalize_text(value)
    for value in (
        "اهلا بك هل نتابع حديثا سابقا",
        "مرحبا اخبرني بما يشغل اهتمامك الان",
        "مرحبا بك ما الموضوع الذي تود التحدث عنه",
        "وعليكم السلام هل جئت بموضوع تريد مناقشته",
        "انا جاهز لمناقشة طلبك",
    )
)
_NON_TOPIC_ANCHORS = {
    normalize_text(value)
    for value in (
        "ماذا", "لماذا", "ما", "ل", "ماخرا", "موخرا",
        "سياق الحوار", "سياق العمل", "اكمل", "حسنا اكمل",
        "تابع", "واصل", "اكمل الحوار", "اكمل الحديث",
    )
}


def _is_social_reset_turn(value: Any, *, role: str = "user") -> bool:
    normalized = normalize_text(_clean(value, 420))
    if not normalized:
        return True
    if normalized in _SOCIAL_RESET_TURNS:
        return True
    if role == "assistant" and any(
        normalized.startswith(prefix) for prefix in _SOCIAL_ASSISTANT_PREFIXES
    ):
        return True
    return False


_LOW_INFORMATION_USER_TURNS = {
    normalize_text(value)
    for value in (
        "كيف الحال", "كيفك", "كيف حالك", "كيف حالك اليوم", "ما أخبارك",
        "أخبارك", "كيف كان نهارك", "كيف قضيت يومك", "كيف داز نهارك",
        "نعم", "أجل", "بلى", "لا", "كلا", "حسنًا", "تمام", "شكرًا",
        "جيد", "جيد جدا", "ممتاز", "الحمد لله", "الحمدلله", "بخير",
        "مرخبا", "ماذا", "لا أعرف ماذا أقول",
        "أكمل", "كمل", "تابع", "واصل", "نكمل", "أكمل الحوار",
        "أكمل الحديث", "سياق الحوار", "سياق العمل",
    )
}
_LOW_INFORMATION_ASSISTANT_PREFIXES = tuple(
    normalize_text(value)
    for value in (
        "أنا بخير، شكرًا لسؤالك",
        "لا أعيش يومًا بالمعنى البشري",
        "أنا جاهز لمناقشة طلبك",
        "حسنًا، أخبرني بما تريد متابعته",
        "حسنًا، لنتحدث بشكل ودي بعيدًا عن العمل والمهام",
        "يمكننا اختيار موضوع خفيف ثم تطوير النقاش بحسب ما يثير اهتمامك",
        "أهلًا بك. هل نتابع حديثًا سابقًا",
        "مرحبًا. أخبرني بما يشغل اهتمامك الآن",
        "سعيد بأنك بخير",
        "يسرني سماع ذلك",
        "جميل،",
        "رائع،",
        "هذا جيد",
        "وعليكم السلام، كيف أساعدك",
    )
)


def _is_non_substantive_turn(value: Any, *, role: str = "user") -> bool:
    """Identify greetings/fillers that cannot serve as the topic to resume."""
    normalized = normalize_text(_clean(value, 420))
    if not normalized or _is_social_reset_turn(value, role=role):
        return True
    if role == "user":
        return normalized in _LOW_INFORMATION_USER_TURNS or normalized in _NON_TOPIC_ANCHORS
    if role == "assistant":
        return any(
            normalized.startswith(prefix)
            for prefix in _LOW_INFORMATION_ASSISTANT_PREFIXES
        )
    return False


def _has_social_only_history(history: list | None) -> bool:
    """Return true only when authorized history exists but contains no topic."""
    eligible = []
    excluded_domains = {"work", "system", "execution", "project", "technical"}
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").casefold()
        if role not in {"user", "assistant"}:
            continue
        content = _clean(turn.get("content"), 420)
        if not content:
            continue
        kind = str(turn.get("context_kind") or "").casefold()
        domain = str(turn.get("conversation_domain") or "").casefold()
        if kind in excluded_domains or domain in excluded_domains:
            return False
        eligible.append((content, role))
    return bool(eligible) and all(
        _is_non_substantive_turn(content, role=role)
        for content, role in eligible
    )


def _is_substantive_anchor(value: Any) -> bool:
    normalized = normalize_text(_clean(value, 420))
    if (
        not normalized
        or normalized in _SOCIAL_RESET_TURNS | _NON_TOPIC_ANCHORS
        or _is_non_substantive_turn(value, role="user")
    ):
        return False
    return len(normalized) > 2


def _history_parts(
    history: list | None,
    *,
    allow_technical: bool = False,
) -> tuple[str, str]:
    """Return the latest completed exchange within the caller-authorized domain."""
    pending_user = ""
    last_pair = ("", "")
    excluded_domains = {"work", "system", "execution", "project"}
    if not allow_technical:
        excluded_domains.add("technical")
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").casefold()
        content = _clean(turn.get("content"), 420)
        if not content:
            continue
        kind = str(turn.get("context_kind") or "").casefold()
        domain = str(turn.get("conversation_domain") or "").casefold()
        if kind in {"work", "system", "execution", "project"} or domain in excluded_domains:
            # Discard a branch outside the owner-authorized history window.
            pending_user = ""
            last_pair = ("", "")
            continue
        if role == "user":
            if _is_social_reset_turn(content, role="user"):
                # A fresh social opening intentionally starts an independent
                # branch; older topic turns must not leak into its continuation.
                pending_user = ""
                last_pair = ("", "")
            elif _is_non_substantive_turn(content, role="user"):
                # Greetings, state questions and bare acknowledgements are not
                # meaningful topic anchors. Keep any earlier substantive pair
                # within the current branch instead of replacing it with small talk.
                pending_user = ""
            else:
                pending_user = content
        elif role == "assistant":
            if pending_user and not _is_non_substantive_turn(content, role="assistant"):
                last_pair = (pending_user, content)
            elif _is_social_reset_turn(content, role="assistant"):
                last_pair = ("", "")
            pending_user = ""
    return last_pair


def _topic(
    parsed: dict,
    semantic: dict,
    history: list | None,
    *,
    allow_technical: bool = False,
) -> str:
    target = _clean(parsed.get("target") or semantic.get("target"), 100)
    if _is_substantive_anchor(target):
        return target
    for turn in reversed(history or []):
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").casefold()
        if _is_social_reset_turn(turn.get("content"), role=role):
            continue
        kind = str(turn.get("context_kind") or "").casefold()
        domain = str(turn.get("conversation_domain") or "").casefold()
        excluded_domains = {"work", "system", "execution", "project"}
        if not allow_technical:
            excluded_domains.add("technical")
        if kind in {"work", "system", "execution", "project"} or domain in excluded_domains:
            continue
        target = _clean(turn.get("target"), 100)
        if _is_substantive_anchor(target):
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
    # The caller's resolved conversation domain governs which historical
    # branches may be reused. General/social replies exclude stale technical
    # context, while an explicitly technical continuation may reuse that branch.
    allow_technical_history = domain == "technical"
    last_user, last_assistant = _history_parts(
        history,
        allow_technical=allow_technical_history,
    )
    topic_parse = parsed
    social_opening_text = any(marker in normalized for marker in (
        "دعنا نتحدث", "لنتحدث قليلا", "لنتحدث قليل", "نتحدث قليلا",
        "محادثه وديه", "دردشه وديه", "نريد ان نتحدث فقط",
        "دردشه فقط", "موضوع خفيف",
    ))
    social_opening_act = act in {
        "SOCIAL_GREETING", "SOCIAL_OPENING", "CASUAL_CONVERSATION",
        "CASUAL_DISCUSSION", "PERSONAL_INTERACTION",
    }
    inherited_target = _clean(parsed.get("target"), 100)
    # A target copied from the previous technical branch is not an explicit
    # topic choice in a new greeting/opening. Resolve the subject from the
    # authorized history instead, where the current domain filter applies.
    if (
        inherited_target
        and normalize_text(inherited_target) not in normalized
        and (social_opening_text or social_opening_act)
        and not allow_technical_history
    ):
        topic_parse = dict(parsed)
        topic_parse["target"] = ""
    topic = _topic(
        topic_parse,
        semantic,
        history,
        allow_technical=allow_technical_history,
    )
    if isinstance(context_entity, dict) and not topic:
        candidate_topic = _clean(context_entity.get("entity"), 100)
        if _is_substantive_anchor(candidate_topic):
            topic = candidate_topic

    if act == "SOCIAL_GREETING":
        # Keep the active subject available when history was explicitly granted;
        # do not claim a new topic or replace it with a generic greeting.
        if topic and last_user:
            reply = (
                f"أهلًا بعودتك إلى الحوار حول «{topic}». "
                "هل تريد متابعة الفكرة السابقة أم النظر إليها من زاوية أخرى؟"
            )
        elif any(word in normalized.split() for word in ("صباح", "صباحا", "صباحًا")):
            reply = "صباح الخير. هل تود بدء يومك بسؤال محدد أم بحوار مفتوح؟"
        elif any(word in normalized.split() for word in ("مساء", "مساءا", "مساءً")):
            reply = "مساء الخير. ما الموضوع الذي يستحق أن نمنحه بعض الوقت اليوم؟"
        elif "السلام" in normalized or normalized.startswith("سلام"):
            reply = "وعليكم السلام. هل جئت بموضوع تريد مناقشته أم نختار موضوعًا معًا؟"
        elif any(word in normalized.split() for word in ("اهلا", "أهلا", "هلا")):
            reply = "أهلًا بك. هل نتابع حديثًا سابقًا أم نبدأ من فكرة جديدة؟"
        else:
            reply = "مرحبًا. أخبرني بما يشغل اهتمامك الآن، وسأتعامل معه بحسب سياقه."
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

    if act == "CONVERSATION_HISTORY_QUERY":
        if not last_user and not last_assistant and not topic:
            return {
                **_result(
                    "لا أجد في سجل الحوار المتاح موضوعًا سابقًا واضحًا لاستعادته. اذكر الموضوع المقصود أو أرسل جزءًا من الحوار.",
                    parsed,
                ),
                "status": "needs_clarification",
            }
        return None

    if act in {"CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY", "TOPIC_RETURN"}:
        if not last_user and not last_assistant and not topic:
            if _has_social_only_history(history):
                result = _result(
                    "كنا نتبادل التحية ونسأل باختصار عن الحال، لكننا لم نحدد موضوعًا للنقاش بعد. "
                    "يمكننا بدء حديث خفيف عن الفن أو الحياة اليومية، أو أخبرني بما يشغلك.",
                    parsed,
                    "local_social_engine",
                )
                result["local_strategy"] = "friendly_dialogue_reopen"
                return result
            return {
                **_result(
                    "لا أجد في السياق المتاح نقطة سابقة موثوقة أتابع منها. اذكر الموضوع أو أرسل جزءًا من الحوار المقصود.",
                    parsed,
                ),
                "status": "needs_clarification",
            }
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
            if last_assistant:
                reply = (
                    f"يمكننا مواصلة الحديث عن «{topic}» بصورة غير رسمية. "
                    f"آخر نقطة طرحتها كانت «{last_user}». "
                    f"وكان الرد السابق: «{last_assistant}». "
                    "أي جانب تريد أن نتابع منه؟"
                )
            else:
                reply = (
                    f"يمكننا مواصلة الحديث عن «{topic}» بصورة غير رسمية. "
                    f"آخر نقطة طرحتها كانت «{last_user}». ما الذي لفت انتباهك فيها؟"
                )
        elif last_user and last_assistant:
            reply = (
                f"يمكننا متابعة الحديث من آخر نقطة طرحتها: «{last_user}». "
                f"وكان الرد السابق: «{last_assistant}». أي جانب تريد أن نتابع منه؟"
            )
        else:
            reply = (
                "يمكننا اختيار موضوع خفيف ثم تطوير النقاش بحسب ما يثير اهتمامك. "
                "هل تفضّل موضوعًا عن الفن، أو الأفكار والحياة اليومية، أو التقنية؟"
            )
        return _result(reply, parsed, "local_social_engine")

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
