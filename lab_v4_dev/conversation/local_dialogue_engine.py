"""Context-aware offline responder for ordinary dialogue.

This module is deliberately not presented as a local language model. It composes
responses from the current conversational act and same-session dialogue memory;
requests requiring unsupported factual knowledge remain eligible for a provider.
"""
from __future__ import annotations

import re
import unicodedata


_SOCIAL_INTENTS = {"personal_chat", "chat", "discussion", "unclear", "help"}
_NON_DIALOGUE_DOMAINS = {"work", "system", "execution", "project", "technical"}


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    return " ".join(text.split()).strip(" .،؛:!?؟")


def _recent_exchanges(memory) -> list[dict]:
    state = getattr(memory, "state", None) if memory else None
    archive = getattr(state, "exchange_archive", []) or []
    session_id = str(getattr(state, "session_id", "") or "")
    result = []
    for item in archive:
        if not isinstance(item, dict) or item.get("recall_only"):
            continue
        if session_id and str(item.get("session_id") or "") != session_id:
            continue
        if str(item.get("context_kind") or "").casefold() in {"work", "system", "execution"}:
            continue
        if str(item.get("conversation_domain") or "").casefold() in _NON_DIALOGUE_DOMAINS:
            continue
        result.append(item)
    return result[-8:]


def _result(text: str, *, act: str, target: str = "") -> dict:
    # Preserve the established source label for the greeting path; the new
    # engine owns broader conversational turns under its explicit source.
    source = "local_social" if act == "SOCIAL_OPENING" else "local_dialogue_engine"
    return {
        "status": "success",
        "intent": "personal_chat",
        "text": text,
        "mode": "CHAT",
        "source": source,
        "conversation_act": act,
        "target": target,
        "executed": False,
    }


def respond_locally(text: str, parsed: dict | None, dialogue_memory=None) -> dict | None:
    """Resolve low-risk social dialogue from semantics and same-session memory."""
    parsed = parsed if isinstance(parsed, dict) else {}
    normalized = _norm(text)
    intent = getattr(parsed.get("intent"), "value", parsed.get("intent"))
    intent = str(intent or "").casefold()
    domain = str(parsed.get("conversation_domain") or "general").casefold()
    act = str(parsed.get("conversation_act") or "NONE").upper()

    identity_request = bool(re.search(
        r"^(من انت|من تكون|ما اسمك|من هو cyberlab agent)$", normalized
    ))
    explicit_continuation = bool(re.fullmatch(
        r"(?:اكمل|استكمل|تابع|واصل|نكمل) (?:الحوار|الحديث|النقاش|المحادثه)",
        normalized,
    ))
    bare_continuation = normalized in {"اكمل", "استكمل", "تابع", "واصل", "نكمل"}
    vague_how = normalized == "كيف"

    exchanges = _recent_exchanges(dialogue_memory)
    last = exchanges[-1] if exchanges else {}
    last_user = str(last.get("user") or "").strip()
    last_assistant = str(last.get("assistant") or "").strip()
    last_user_norm = _norm(last_user)
    last_assistant_norm = _norm(last_assistant)

    # A previous social turn is not enough if the latest recorded exchange
    # belongs to work/system/technical routing. Continuation ownership must be
    # based on the latest real exchange, not any older eligible item.
    state = getattr(dialogue_memory, "state", None) if dialogue_memory else None
    archive = getattr(state, "exchange_archive", []) or []
    session_id = str(getattr(state, "session_id", "") or "")
    latest_record = next((
        item for item in reversed(archive)
        if isinstance(item, dict)
        and not item.get("recall_only")
        and not item.get("state_boundary_only")
        and (not session_id or str(item.get("session_id") or "") == session_id)
    ), {})
    latest_domain = str(latest_record.get("conversation_domain") or "").casefold()
    latest_kind = str(latest_record.get("context_kind") or "").casefold()
    latest_is_dialogue = bool(
        latest_record
        and latest_domain not in _NON_DIALOGUE_DOMAINS
        and latest_kind not in {"work", "system", "execution"}
    )

    wellbeing_answer = bool(re.search(
        r"^(بخير|انا بخير|الحمد لله|تمام|جيد|جيدة|بخير شكرا|بخير شكرا لك|"
        r"الحمد لله بخير|كل شيء بخير)$",
        normalized,
    ))
    previous_check_in = any(marker in last_assistant_norm for marker in (
        "كيف حالك", "كيف تسير امورك", "كيف كان يومك", "كيف كان الحال",
    ))
    contextual_wellbeing_reply = (
        wellbeing_answer and previous_check_in and latest_is_dialogue
    )

    # Explicit dialogue continuation is allowed through a parser fallback that
    # labels the phrase as resume/system, but only when the latest recorded turn
    # is actually dialogue-owned. A bare "continue" follows the same rule.
    continuation_turn = (
        (explicit_continuation or bare_continuation)
        and latest_is_dialogue
        and bool(exchanges)
    )
    if (
        not identity_request
        and not continuation_turn
        and not vague_how
        and not contextual_wellbeing_reply
        and (
            domain in _NON_DIALOGUE_DOMAINS or intent not in _SOCIAL_INTENTS
        )
    ):
        return None

    if re.search(r"^(من انت|من تكون|ما اسمك|من هو cyberlab agent)$", normalized):
        return _result(
            "أنا CyberLab Agent، وكيل برمجي يعمل عبر مسارات محلية ومزودات خارجية مهيأة. "
            "يمكنني معالجة بعض الحوار واسترجاع المعلومات المحفوظة محليًا دون اتصال؛ "
            "لكنني لا أملك نموذجًا لغويًا محليًا عامًا مثبتًا، لذلك تعتمد الأسئلة التي "
            "تتطلب معرفة غير محفوظة أو توليدًا مفتوحًا على توفر مزود خارجي.",
            act="AGENT_IDENTITY",
        )

    if re.search(r"^(مرحبا|اهلا|السلام عليكم|صباح الخير|مساء الخير|يا هلا)$", normalized):
        return _result(
            "مرحبًا بك. يمكننا التحدث بحرية، أو متابعة موضوع محفوظ في سياق هذه الجلسة. "
            "ما الذي تود أن نبدأ به؟",
            act="SOCIAL_OPENING",
        )

    if re.search(
        r"^(كيفك|كيف الحال|كيف هي الاحوال|كيف الاحوال|كيف حالك|كيف اخبارك|"
        r"ما اخبارك|ما الاخبار|كيف تسير امورك)$",
        normalized,
    ):
        return _result(
            "أنا جاهز للمحادثة ومساعدتك قدر ما تسمح به المعلومات المتاحة محليًا. "
            "كيف تسير أمورك أنت؟",
            act="SOCIAL_CHECK_IN",
        )

    # Acknowledge the user's answer to a previous check-in using the actual turn,
    # rather than replaying a canned greeting or the previous assistant sentence.
    if contextual_wellbeing_reply:
        return _result(
            "سعيد بأن أمورك بخير. يمكننا مواصلة الحديث بهدوء؛ هل حدث معك شيء اليوم "
            "تود الحديث عنه، أم تفضّل أن نختار موضوعًا للنقاش؟",
            act="SOCIAL_ACKNOWLEDGEMENT",
        )

    if vague_how:
        return _result(
            "كلمة «كيف؟» وحدها لا تحدد ما الذي تسأل عنه. هل تقصد السؤال عن الحال، "
            "أم تريد معرفة كيفية حدوث شيء محدد؟",
            act="CLARIFICATION_REQUEST",
        )

    if continuation_turn:
        if not exchanges:
            return _result(
                "لا يظهر في ذاكرة هذه الجلسة حوار سابق كافٍ لاستكماله. "
                "اذكر الموضوع الذي تريد العودة إليه.",
                act="CONVERSATION_CONTINUATION",
            )
        named_topic = next(
            (str(item.get("target") or "").strip()
             for item in reversed(exchanges)
             if str(item.get("target") or "").strip()),
            "",
        )
        if named_topic:
            return _result(
                f"آخر موضوع حواري محفوظ هو «{named_topic}». "
                "لا يظهر في السجل ما يكفي لتحديد نقطة شرح أدق دون افتراضات. "
                "أي جانب من الموضوع تريد أن نتابع؟",
                act="CONVERSATION_CONTINUATION",
                target=named_topic,
            )
        social_only = all(
            _norm(item.get("user") or "") in {
                "مرحبا", "اهلا", "السلام عليكم", "كيف الحال", "كيفك",
                "كيف حالك", "كيف هي الاحوال", "كيف الاحوال", "بخير",
                "بخير شكرا", "انا بخير", "الحمد لله", "تمام",
            }
            for item in exchanges[-4:]
        )
        if social_only:
            return _result(
                "حتى الآن تبادلنا التحية وتحدثنا عن الحال، ولم نحدد موضوعًا للنقاش بعد. "
                "يمكننا الحديث عن الفن أو الحياة اليومية أو أي موضوع تختاره.",
                act="CONVERSATION_CONTINUATION",
            )
        excerpt = last_assistant[:220].strip()
        return _result(
            "سأتابع من آخر نقطة مسجلة في الحوار: "
            + (f"«{excerpt}»." if excerpt else "لم تُحفظ إجابة سابقة واضحة.")
            + " ما الجانب الذي تريد التوسع فيه؟",
            act="CONVERSATION_CONTINUATION",
            target=str(last.get("target") or ""),
        )

    if re.search(r"^(لنتحدث قليلا|لنتحدث قليلا|دعنا نتحدث|اريد ان اتحدث|"
                 r"اريد التحدث|نتحدث قليلا|دردشة|دردشه|خلينا نتحدث)$", normalized):
        topic = str(last.get("target") or "").strip()
        if topic and last_assistant:
            return _result(
                f"بكل سرور. أرى أن آخر موضوع حواري محفوظ هو «{topic}»، ويمكننا العودة إليه "
                "أو بدء موضوع جديد. أيهما تفضّل؟",
                act="CASUAL_CONVERSATION",
                target=topic,
            )
        return _result(
            "بكل سرور. لنبدأ حديثًا عاديًا بعيدًا عن المهام التقنية. يمكننا مناقشة "
            "الأفكار أو الفن أو الحياة اليومية، أو يمكنك اختيار أي موضوع يهمك.",
            act="CASUAL_CONVERSATION",
        )

    if normalized in {"ماذا", "ما هذا", "لم افهم", "ماذا تقصد", "وضح", "وضح اكثر"}:
        if last_assistant:
            excerpt = re.split(r"(?<=[.!؟])\s+", last_assistant, maxsplit=1)[0][:220]
            return _result(
                f"يبدو أنك تطلب توضيح ردي السابق، لا بدء موضوع جديد. النقطة التي أشرت إليها هي: "
                f"«{excerpt}». أي جزء منها تريد توضيحه تحديدًا؟",
                act="CLARIFICATION_REQUEST",
                target=str(last.get("target") or ""),
            )
        return _result(
            "أحتاج إلى معرفة ما الذي تشير إليه كلمة «ماذا؟». لا يظهر في ذاكرة الحوار "
            "المحلية سياق كافٍ لتحديد المقصود.",
            act="CLARIFICATION_REQUEST",
        )

    if act in {"SOCIAL_ACKNOWLEDGEMENT", "CASUAL_CONVERSATION", "SOCIAL_OPENING"}:
        # For context-sensitive short turns, derive a follow-up from the last
        # exchange only when that exchange exists and is clearly dialogue-owned.
        if last_user and last_assistant and normalized in {"حسنا", "تمام", "طيب", "شكرا", "شكرا لك"}:
            topic = str(last.get("target") or "").strip()
            if topic:
                return _result(
                    f"حسنًا، نتابع من سياق «{topic}». ما الجانب الذي تريد استكشافه بعد ذلك؟",
                    act=act,
                    target=topic,
                )
            return _result(
                "حسنًا. سأبقي الحديث ضمن سياقه بدل افتراض موضوع جديد. ما النقطة التي تود أن نتابع منها؟",
                act=act,
            )

    # Substantive factual questions are not guessed from conversational patterns.
    # The caller may route these to a configured provider after local retrieval.
    return None
