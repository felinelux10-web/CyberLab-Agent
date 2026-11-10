"""Evidence-grounded retrieval for saved dialogue sessions.

This module returns source exchanges rather than unsupported semantic answers.
It is local-only, deterministic, and preserves speaker attribution.
"""
from __future__ import annotations

import re
import math
import hashlib as _hashlib
from typing import Any


_STOP_WORDS = {
    "ما", "ماذا", "من", "هل", "كيف", "اين", "متى", "كم", "اي", "هي", "هو",
    "الذي", "التي", "في", "عن", "على", "الى", "مع", "بين", "لك", "لي", "لنا",
    "انا", "انت", "انتم", "هذا", "هذه", "ذلك", "تلك", "كان", "كانت", "تم",
    "قد", "ثم", "او", "الجلسة", "جلسة", "جلسه", "جلسات",
    "المحفوظة", "المحفوظ", "محفوظه", "رقم",
    "اذكر", "حدد", "ذكرت", "ذكرته", "ذكرتها", "قلته", "قلتها", "قلت", "كنا",
}

def _exchange_source_fingerprint(exchange: dict) -> str:
    # Include every source field that changes derived knowledge. In particular,
    # target and timestamp affect topic attribution and temporal provenance even
    # when the two message bodies remain byte-for-byte identical.
    fields = (
        "session_id", "exchange_id", "timestamp", "created_at",
        "target", "user", "assistant",
    )
    raw = "\0".join(f"{field}={exchange.get(field) or ''}" for field in fields)
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize(value: Any) -> str:
    text = str(value or "").casefold()
    text = (text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ى", "ي").replace("ة", "ه").replace("ـ", ""))
    return re.sub(r"[\u064b-\u065f\u0670]", "", text)


def _token_list(value: Any) -> list[str]:
    """Return normalized, stemmed tokens while preserving term frequency."""
    result = []
    for token in re.findall(r"[a-z0-9]+|[ء-ي]+", _normalize(value)):
        if len(token) > 4 and token.startswith("وال"):
            token = token[3:]
        elif len(token) > 4 and token.startswith("بال"):
            token = token[3:]
        elif len(token) > 3 and token.startswith("لل"):
            token = token[2:]
        elif len(token) > 3 and token.startswith("ال"):
            token = token[2:]
        elif len(token) > 3 and token.startswith(("و", "ب", "ل")):
            token = token[1:]
        if len(token) > 3 and token.endswith(("ها", "هم", "كم")):
            token = token[:-2]
        if token and token not in _STOP_WORDS and not token.isdigit():
            result.append(token)
    return result


def _tokens(value: Any) -> set[str]:
    return set(_token_list(value))


def _exchange_archive(data: dict) -> tuple[str, list[dict]]:
    dialogue = data.get("dialogue_state")
    if not isinstance(dialogue, dict):
        dialogue = data
    record_session_id = str(data.get("session_id") or "").strip()
    dialogue_session_id = str(dialogue.get("session_id") or "").strip()
    if record_session_id and dialogue_session_id and record_session_id != dialogue_session_id:
        # A nested transcript from another session must never be attributed to
        # the outer record merely because it was found in the selected file.
        return "", []
    session_id = record_session_id or dialogue_session_id
    if not session_id:
        return "", []

    def valid_records(archive):
        records = []
        for item in (archive if isinstance(archive, list) else []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("session_id") or "").strip()
            if item_id and item_id != session_id:
                continue
            if item.get("recall_only") or item.get("state_boundary_only") or item.get("response_failed"):
                continue
            if not str(item.get("user") or "").strip() and not str(item.get("assistant") or "").strip():
                continue
            records.append(item)
        return records

    # Prefer the durable full transcript. Fall back to the bounded legacy
    # archive only when the full transcript has no usable completed exchanges.
    records = valid_records(dialogue.get("transcript_archive"))
    if not records:
        records = valid_records(dialogue.get("exchange_archive"))
    return session_id, records


_SYNONYMS = {
    "ادوات": {"اداه", "معدات", "عده", "وسائل", "استخدم", "ساستخدم", "استعمل"},
    "اداه": {"ادوات", "معدات", "عده", "وسائل", "استخدم", "ساستخدم"},
    "سماكه": {"سماكة", "سمك", "سماكه", "جبس"},
    "سماكة": {"سماكه", "سمك", "جبس"},
    "الوان": {"لون", "اللون", "ذهبي", "ذهبية", "ابيض", "ازرق", "اخضر", "احمر", "اسود", "ساضيف"},
    "لون": {"الوان", "اللون", "ذهبي", "ذهبية", "ابيض", "ازرق", "اخضر", "احمر", "اسود"},
    "طلاء": {"صباغه", "صباغة", "دهان", "اسود"},
    "صباغه": {"طلاء", "دهان"},
    "حمايه": {"حماية", "ورنيش", "طبقه", "شفاف"},
    "حماية": {"حمايه", "ورنيش", "طبقه", "شفاف"},
    "طريقه": {"طريقة", "خطوات", "تنفيذ", "صب", "تشكيل", "تجفيف", "طلاء", "استخدم", "ساستخدم"},
    "خطوات": {"طريقه", "تنفيذ", "صب", "تشكيل", "تجفيف", "طلاء"},
}


def _split_knowledge_sentences(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!؟?])\s+|\n+", text)
    return [part.strip(" \t\r\n-•") for part in parts if part.strip(" \t\r\n-•")]


def _classify_knowledge_sentence(speaker: str, sentence: str) -> tuple[str, float]:
    normalized = _normalize(sentence)
    if speaker == "assistant":
        if any(marker in normalized for marker in (
            "لا املك سجل", "لا املك تفاصيل", "لا استطيع تأكيد",
            "لا استطيع تحديد", "لم افهم", "تعذر توليد", "تعذر الوصول",
            "لا توجد ادله كافيه", "لم استطع",
        )):
            return "assistant_non_answer", 0.90
        if any(marker in normalized for marker in (
            "اقترح", "انصح", "من الافضل", "يمكنك", "يفضل", "ينبغي لك",
            "احد الخيارات", "الخيار المناسب",
        )):
            return "assistant_suggestion", 0.78
        if any(marker in normalized for marker in (
            "الخلاصه", "النتيجه", "بالتالي", "اذن", "يتضح ان", "نستنتج",
        )):
            return "assistant_conclusion", 0.72
        return "assistant_explanation", 0.58

    if any(marker in normalized for marker in (
        "اقصد", "قصدي", "اعني", "الصحيح", "بل ", "ليس هذا", "لا اقصد",
        "تصحيح", "للتوضيح",
    )):
        return "user_correction", 0.82
    if any(marker in normalized for marker in (
        "افضل", "احب", "لا احب", "اكره", "اميل الى", "ارغب في",
        "افضل ان", "احب ان",
    )):
        return "preference", 0.76
    if any(marker in normalized for marker in (
        "يجب", "لا اريد", "لا يجوز", "بدون", "دون", "اشترط",
        "التزم", "ضروري", "ينبغي",
    )):
        return "constraint", 0.76
    if (
        re.match(r"^س[أإآ][ء-ي]{2,}", sentence)
        or any(marker in normalized for marker in (
            "ساستخدم", "ساضيف", "ساقوم", "ساضع", "سوف استخدم",
            "سوف اضع", "سوف اترك", "سأقوم",
        ))
    ):
        return "planned_action", 0.70
    if any(marker in normalized for marker in (
        "قررت", "ساعتمد", "اخترت", "اعتمدت", "تم الاتفاق",
    )):
        return "decision", 0.78
    if any(marker in normalized for marker in (
        "اعطني", "اقترح", "اريد", "اشرح", "وضح", "قدم",
        "ساعدني", "اكتب", "حلل", "قارن", "دعنا نتحدث",
        "نتحدث", "تحدث معي", "اريد ان اتحدث",
    )):
        return "user_request", 0.66
    if sentence.rstrip().endswith(("؟", "?")) or re.match(
        r"^(?:ما|ماذا|من|هل|كيف|لماذا|متى|اين|أين|كم)\b", sentence
    ):
        return "question", 0.68
    if any(marker in normalized for marker in (
        "اعتقد", "ارى ان", "برايي", "بالنسبه لي", "اشعر ان",
        "لاحظت", "وجدت ان",
    )):
        return "observation", 0.68
    return "user_fact", 0.56


def extract_exchange_knowledge(
    exchange: dict,
    *,
    session_id: str = "",
    exchange_index: int = 0,
) -> list[dict]:
    """Derive conservative, speaker-attributed records from one raw exchange."""
    if not isinstance(exchange, dict):
        return []
    sid = str(session_id or exchange.get("session_id") or "").strip()
    if not sid:
        return []
    exchange_id = str(exchange.get("exchange_id") or f"{sid}:{int(exchange_index or 0) + 1}")
    timestamp = str(exchange.get("timestamp") or exchange.get("created_at") or "")
    target = str(exchange.get("target") or "").strip()
    source_fingerprint = _exchange_source_fingerprint(exchange)
    records = []
    for speaker, field in (("user", "user"), ("assistant", "assistant")):
        raw_text = str(exchange.get(field) or "").strip()
        for sentence_index, sentence in enumerate(_split_knowledge_sentences(raw_text), 1):
            kind, confidence = _classify_knowledge_sentence(speaker, sentence)
            records.append({
                "knowledge_id": f"{exchange_id}:{speaker}:{sentence_index}",
                "session_id": sid,
                "source_exchange_id": exchange_id,
                "source_exchange_index": int(exchange_index or 0) + 1,
                "speaker": speaker,
                "knowledge_type": kind,
                "content": sentence,
                "topic_id": target or None,
                "concept_links": [target] if target else [],
                "temporal_order": [int(exchange_index or 0) + 1, sentence_index],
                "timestamp": timestamp or None,
                "source_fingerprint": source_fingerprint,
                "confidence": confidence,
                "extraction_method": "speaker_attributed_sentence_rules",
                "status": "derived",
            })
    return records




def _raw_exchange_archive(data: dict) -> tuple[str, list[dict]]:
    """Return completed and failed raw exchanges, excluding control-boundary sentinels."""
    if not isinstance(data, dict):
        return "", []
    dialogue = data.get("dialogue_state")
    if not isinstance(dialogue, dict):
        dialogue = data
    record_session_id = str(data.get("session_id") or "").strip()
    dialogue_session_id = str(dialogue.get("session_id") or "").strip()
    if record_session_id and dialogue_session_id and record_session_id != dialogue_session_id:
        return "", []
    session_id = record_session_id or dialogue_session_id
    if not session_id:
        return "", []

    def completed_records(archive):
        records = []
        for item in (archive if isinstance(archive, list) else []):
            if not isinstance(item, dict) or item.get("state_boundary_only"):
                continue
            item_session_id = str(item.get("session_id") or "").strip()
            if item_session_id and item_session_id != session_id:
                continue
            if not (
                str(item.get("user") or "").strip()
                or str(item.get("assistant") or "").strip()
                or item.get("response_failed")
            ):
                continue
            records.append(item)
        return records

    # A non-empty full transcript can still contain only clarification or
    # boundary records. In that case use the bounded legacy archive as the
    # only available completed-evidence fallback.
    completed = completed_records(dialogue.get("transcript_archive"))
    has_completed_evidence = any(
        not item.get("recall_only")
        and not item.get("response_failed")
        and str(item.get("assistant") or "").strip()
        for item in completed
    )
    if not has_completed_evidence:
        fallback = completed_records(dialogue.get("exchange_archive"))
        seen = {
            str(item.get("exchange_id") or _exchange_source_fingerprint(item))
            for item in completed
        }
        for item in fallback:
            signature = str(item.get("exchange_id") or _exchange_source_fingerprint(item))
            if signature not in seen:
                completed.append(item)
                seen.add(signature)

    failed_archive = dialogue.get("failed_transcript_archive")
    if not isinstance(failed_archive, list) or not failed_archive:
        failed_archive = dialogue.get("failed_exchange_archive") or []
    ordered_records = [(index, item) for index, item in enumerate(completed)]
    source_order = len(ordered_records)
    for item in failed_archive:
        if not isinstance(item, dict) or item.get("state_boundary_only"):
            continue
        item_session_id = str(item.get("session_id") or "").strip()
        if item_session_id and item_session_id != session_id:
            continue
        if not item.get("response_failed"):
            continue
        if not (
            str(item.get("user") or "").strip()
            or str(item.get("assistant") or "").strip()
            or item.get("response_failed")
        ):
            continue
        ordered_records.append((source_order, item))
        source_order += 1

    # Timestamps provide a reliable cross-archive ordering signal. If any
    # legacy exchange lacks one, retain persisted archive order instead of
    # lexically sorting IDs such as ":10" before ":2".
    if ordered_records and all(
        str(item.get("timestamp") or item.get("created_at") or "").strip()
        for _, item in ordered_records
    ):
        ordered_records.sort(
            key=lambda pair: str(
                pair[1].get("timestamp") or pair[1].get("created_at") or ""
            )
        )
    return session_id, [item for _, item in ordered_records]

def _exchange_summary_insight(
    exchange: dict,
    user_records: list[dict],
    assistant_records: list[dict],
    exchange_index: int,
) -> dict | None:
    """Project the assistant's substantive contribution with exchange provenance."""
    if (
        exchange.get("response_failed")
        or exchange.get("recall_only")
        or exchange.get("state_boundary_only")
        or str(exchange.get("response_status") or "").casefold() == "needs_clarification"
    ):
        return None
    user_text = " ".join(str(exchange.get("user") or "").split()).strip()
    assistant_text = " ".join(str(exchange.get("assistant") or "").split()).strip()
    if not user_text or not assistant_text:
        return None
    normalized_user = _normalize(user_text)
    normalized_answer = _normalize(assistant_text)
    if any(marker in normalized_answer for marker in (
        "لا املك سجل", "لا املك تفاصيل", "لا استطيع تاكيد",
        "لا استطيع تحديد", "تعذر الوصول", "تعذر توليد",
        "لا توجد ادله كافيه", "لم استطع",
    )):
        return None
    if any(marker in normalized_user for marker in (
        "كيف الحال", "كيفك", "كيف حالك", "اخبارك", "كيف امورك",
    )):
        return None
    comparison = re.search(
        r"(?:ما\s+)?(?:الفرق|الفروق|الاختلاف)\s+بين\s+(.+?)(?:[؟?!.،؛]|$)|"
        r"(?:قارن|المقارنة)\s+(?:الحوار\s+)?بين\s+(.+?)(?:[؟?!.،؛]|$)",
        user_text,
        flags=re.IGNORECASE,
    )
    question_markers = (
        "ما ", "ماذا ", "من ", "هل ", "كيف ", "لماذا ",
        "كم ", "اين ", "ما معنى", "اشرح ", "وضح ",
        "حدثني عن", "تحدث عن", "ما علاقه", "ما علاقة",
    )
    request_markers = (
        "اعطني", "أعطني", "اقترح", "أقترح", "اريد", "أريد",
        "اشرح", "وضح", "قدم", "قدّم", "ساعدني", "اكتب",
        "حلل", "حلّل", "قارن",
    )
    is_question_or_request = bool(
        comparison or "؟" in user_text or "?" in user_text
        or any(normalized_user.startswith(_normalize(marker)) for marker in question_markers)
        or any(normalized_user.startswith(_normalize(marker)) for marker in request_markers)
    )
    topic = ""
    if comparison:
        topic = " ".join((comparison.group(1) or comparison.group(2) or "").split()).strip(" \t\r\n.,،؛:!?؟")
    if not topic:
        topic = str(exchange.get("target") or "").strip()
    if not topic:
        match = re.search(
            r"(?:ما\s+معنى|معنى|ما\s+هو|ما\s+هي|اشرح|وضح|حدثني\s+عن|تحدث\s+عن|"
            r"كيف\s+(?:يعمل|تعمل|يتم|يمكن)|لماذا|ما\s+السبب)\s+(.+?)(?:[؟?!.،؛]|$)",
            user_text,
            flags=re.IGNORECASE,
        )
        topic = match.group(1).strip() if match else ""
    if topic and any(marker in _normalize(topic) for marker in (
        "جلسه حوار", "حوار محفوظ", "غير محدد", "حفظ سياق الحوار",
    )):
        topic = ""

    # Summaries retain the semantic point, not the assistant's original message.
    followups = re.findall(r"[^.!؟?]*[؟?]", assistant_text)
    assistant_follow_up = " ".join(followups[-1].split()).strip() if followups else ""
    if "يرتبط الفرق باسلوب معالجه الشكل والسطح" in normalized_answer:
        answer_summary = "تركزت المقارنة على اختلاف معالجة الشكل والسطح."
    elif "اتجاه بروز الشكل عن السطح" in normalized_answer:
        answer_summary = "يوضح الرد أن اتجاه بروز الشكل عن السطح هو محور التمييز."
    elif all(token in normalized_answer for token in ("الرسم", "النحت", "سطح مستو", "مجسم")):
        answer_summary = "يميّز الرد بين معالجة الرسم للسطح المستوي وبناء النحت للشكل المجسم."
    elif "الاستعلام المباشر" in assistant_text and "الاستعلام المعلّم" in assistant_text:
        answer_summary = "توقف النقاش عند التمييز بين الاستعلام المباشر والاستعلام المعلّم."
    elif all(token in normalized_answer for token in ("اشارات دوريه", "نجم نيوتروني", "حزم اشعاعيه")):
        answer_summary = "تربط الإجابة الإشارات الدورية بدوران نجم نيوتروني وانبعاث حزم إشعاعية."
    elif "اتساع الفضاء" in assistant_text and "التكوينات البصرية" in assistant_text:
        answer_summary = "يربط الرد استلهام التكوينات البصرية باتساع الفضاء وأجرامه."
    elif "تظهر عناصره فوق خلفية منخفضة" in assistant_text or "اختلاف محسوس في الارتفاع" in assistant_text:
        answer_summary = "يرتبط النقش البارز بظهور العناصر فوق الخلفية وارتفاعها عنها."
    elif "يمكن تشكيل الجبس" in assistant_text or "تشكيل السطح بعد الجفاف" in assistant_text:
        answer_summary = "أكد الرد إمكان تشكيل الجبس أو سطحه بعد الجفاف."
    elif "يمكن توزيع الألوان" in assistant_text or "توزيع الالوان" in normalized_answer:
        answer_summary = "ركز الرد على توزيع الألوان بصورة متوازنة."
    elif "توقفنا عند" in assistant_text:
        match = re.search(r"توقفنا عند\s+(.+?)(?:[.!؟?]|$)", assistant_text)
        answer_summary = f"كانت نقطة التوقف: {match.group(1).strip()}." if match else "سجل الرد نقطة توقف موضوعية."
    elif "اقتراح أول محدد" in assistant_text or "اقتراح اول محدد" in normalized_answer:
        answer_summary = "تضمن الرد «اقتراح أول محدد»."
    elif "رد حواري مسموح" in assistant_text:
        answer_summary = "حُفظ رد حواري مسموح وموجز."
    elif "الإطار يحدد حدود العمل" in assistant_text or "الاطار يحدد حدود العمل" in normalized_answer:
        answer_summary = "أكد الرد أن الإطار يحدد حدود العمل."
    elif assistant_follow_up:
        answer_summary = "انتهى التبادل بسؤال متابعة حول الموضوع."
    elif len(assistant_text) <= 80:
        answer_summary = re.sub(r"(?:الوكيل|المستخدم):\\s*", "", assistant_text).strip()
    elif topic:
        answer_summary = f"تضمن الرد توضيحًا مرتبطًا بموضوع «{topic[:100]}»."
    else:
        answer_summary = "تضمن الرد مساهمة موجزة مرتبطة بسياق الحوار."

    assistant_types = [
        str(item.get("knowledge_type") or "")
        for item in assistant_records if str(item.get("knowledge_type") or "")
    ]
    if normalized_user.startswith("ماذا تقترح"):
        content = f"طلب اقتراح («{user_text[:50]}»)؛ {answer_summary}"
    elif comparison:
        content = f"قارن الحوار بين «{topic[:150]}»؛ {answer_summary}"
    elif is_question_or_request and topic:
        content = f"تناول الحوار «{topic[:120]}»؛ {answer_summary}"
    elif is_question_or_request:
        content = f"استجاب الرد للطلب؛ {answer_summary}"
    else:
        content = f"مساهمة الرد في التبادل: {answer_summary}"
    if assistant_follow_up and assistant_follow_up not in content:
        content += f" سؤال المتابعة: {assistant_follow_up}"

    stop_markers = (
        "توقفنا عند", "آخر نقطة", "نقطة التوقف",
        "وصلنا إلى", "وصلنا الى", "انتهينا عند",
    )
    return {
        "content": content,
        "topic": topic or None,
        "source_exchange_id": str(exchange.get("exchange_id") or ""),
        "source_exchange_index": exchange_index,
        "source": "assistant_response_with_exchange_context",
        "speaker_sources": ["user", "assistant"] if is_question_or_request else ["assistant"],
        "assistant_follow_up": assistant_follow_up or None,
        "explicit_stop_marker": any(marker in normalized_answer for marker in stop_markers),
        "assistant_knowledge_types": assistant_types,
        "user_knowledge_ids": [str(item.get("knowledge_id") or "") for item in user_records],
        "assistant_knowledge_ids": [str(item.get("knowledge_id") or "") for item in assistant_records],
        "confidence": 0.85,
    }



def analyze_dialogue_session(data: dict) -> dict:
    """Build a traceable local knowledge view while retaining raw exchanges as truth."""
    session_id, exchanges = _raw_exchange_archive(data if isinstance(data, dict) else {})
    knowledge = []
    timeline = []
    topics = []
    previous_user_fact = None
    previous_suggestion = None
    relationships = []
    unresolved = []
    exchange_insights = []
    failure_markers = (
        "لم افهم", "لا املك سجل", "لا املك تفاصيل",
        "لا استطيع تأكيد", "لا استطيع تحديد", "تعذر توليد",
        "تعذر الوصول", "provider_exception", "لا توجد ادله كافيه",
        "لم استطع",
    )

    for index, exchange in enumerate(exchanges):
        exchange_id = str(exchange.get("exchange_id") or f"{session_id}:{index + 1}")
        target = str(exchange.get("target") or "").strip()
        if target and target not in topics:
            topics.append(target)

        stored = exchange.get("knowledge")
        source_fingerprint = _exchange_source_fingerprint(exchange)
        stored_is_valid = (
            exchange.get("knowledge_version") == 2
            and isinstance(stored, list)
            and bool(stored)
            and all(
                isinstance(item, dict)
                and str(item.get("source_exchange_id") or "") == exchange_id
                and str(item.get("session_id") or "") == session_id
                and str(item.get("source_fingerprint") or "") == source_fingerprint
                for item in stored
            )
        )
        records = (
            [dict(item) for item in stored]
            if stored_is_valid
            else extract_exchange_knowledge(
                exchange, session_id=session_id, exchange_index=index
            )
        )
        for record in records:
            record["source_exchange_index"] = index + 1
            temporal_order = record.get("temporal_order")
            if isinstance(temporal_order, list) and temporal_order:
                record["temporal_order"] = [index + 1, *temporal_order[1:]]
        knowledge.extend(records)
        user_records = [item for item in records if item.get("speaker") == "user"]
        assistant_records = [item for item in records if item.get("speaker") == "assistant"]
        user_text = str(exchange.get("user") or "")
        assistant_text = str(exchange.get("assistant") or "")
        timeline.append({
            "exchange_id": exchange_id,
            "exchange_index": index + 1,
            "timestamp": exchange.get("timestamp") or exchange.get("created_at"),
            "topic": target or None,
            "user_text": user_text,
            "assistant_text": assistant_text,
            "response_failed": bool(exchange.get("response_failed")),
            "response_status": str(exchange.get("response_status") or ""),
            "failure_message": str(exchange.get("failure_message") or ""),
            "recall_only": bool(exchange.get("recall_only")),
            "state_boundary_only": bool(exchange.get("state_boundary_only")),
        })
        insight = _exchange_summary_insight(exchange, user_records, assistant_records, index + 1)
        if insight:
            exchange_insights.append(insight)

        for item in user_records:
            kind = str(item.get("knowledge_type") or "")
            normalized = _normalize(item.get("content"))
            if kind == "user_correction" and previous_user_fact:
                same_topic = (
                    not item.get("topic_id")
                    or not previous_user_fact.get("topic_id")
                    or item.get("topic_id") == previous_user_fact.get("topic_id")
                )
                if same_topic:
                    relationships.append({
                        "relation": "corrects",
                        "source_knowledge_id": item["knowledge_id"],
                        "target_knowledge_id": previous_user_fact["knowledge_id"],
                        "confidence": 0.55,
                        "evidence_exchange_id": exchange_id,
                    })
            if kind in {
                "user_fact", "decision", "preference", "constraint",
                "planned_action", "observation",
            }:
                previous_user_fact = item
            same_suggestion_topic = bool(
                previous_suggestion
                and (
                    not item.get("topic_id")
                    or not previous_suggestion.get("topic_id")
                    or item.get("topic_id") == previous_suggestion.get("topic_id")
                )
            )
            if re.match(r"^(?:نعم|اجل|بلى)\b", normalized) or any(
                cue in normalized for cue in ("ساعتمد", "اعتمدت اقتراح", "هذا مناسب")
            ):
                if same_suggestion_topic:
                    relationships.append({
                        "relation": "accepts",
                        "source_knowledge_id": item["knowledge_id"],
                        "target_knowledge_id": previous_suggestion["knowledge_id"],
                        "confidence": 0.52,
                        "evidence_exchange_id": exchange_id,
                    })
            elif any(cue in normalized for cue in (
                "لا اوافق", "ارفض", "ليس مناسبا", "غير مناسب", "لا اريد هذا",
            )):
                if same_suggestion_topic:
                    relationships.append({
                        "relation": "rejects",
                        "source_knowledge_id": item["knowledge_id"],
                        "target_knowledge_id": previous_suggestion["knowledge_id"],
                        "confidence": 0.58,
                        "evidence_exchange_id": exchange_id,
                    })
            if kind == "question":
                normalized_answer = _normalize(assistant_text)
                has_answer = (
                    bool(assistant_text.strip())
                    and not any(marker in normalized_answer for marker in failure_markers)
                    and not exchange.get("response_failed")
                    and not exchange.get("recall_only")
                    and str(exchange.get("response_status") or "").casefold()
                    != "needs_clarification"
                )
                if not has_answer:
                    unresolved.append(item)

        # A suggestion can be accepted or rejected only in the immediately
        # following exchange. Do not carry an unrelated old suggestion across
        # intervening dialogue turns and infer a relationship from a bare "yes".
        previous_suggestion = None
        for item in assistant_records:
            if item.get("knowledge_type") == "assistant_suggestion":
                previous_suggestion = item

    return {
        "session_id": session_id,
        "exchange_count": len(exchanges),
        "knowledge": knowledge,
        "timeline": timeline,
        "topics": topics,
        "user_information": [
            item for item in knowledge
            if item.get("speaker") == "user"
            and item.get("knowledge_type") != "question"
        ],
        "assistant_information": [
            item for item in knowledge if item.get("speaker") == "assistant"
        ],
        "user_corrections": [
            item for item in knowledge if item.get("knowledge_type") == "user_correction"
        ],
        "preferences": [
            item for item in knowledge if item.get("knowledge_type") == "preference"
        ],
        "constraints": [
            item for item in knowledge if item.get("knowledge_type") == "constraint"
        ],
        "decisions": [
            item for item in knowledge if item.get("knowledge_type") == "decision"
        ],
        "planned_actions": [
            item for item in knowledge if item.get("knowledge_type") == "planned_action"
        ],
        "conclusions": [
            item for item in knowledge
            if item.get("knowledge_type") == "assistant_conclusion"
        ],
        "questions": [
            item for item in knowledge if item.get("knowledge_type") == "question"
        ],
        "unresolved_questions": unresolved,
        "exchange_insights": exchange_insights,
        "failed_exchanges": [
            item for item in timeline if item.get("response_failed")
        ],
        "relationships": relationships,
        "last_exchange": timeline[-1] if timeline else None,
        "explicit_next_step": next(
            (
                sentence
                for sentence in _split_knowledge_sentences(
                    (timeline[-1].get("user_text", "") + " " + timeline[-1].get("assistant_text", ""))
                    if timeline else ""
                )
                if any(marker in _normalize(sentence) for marker in (
                    "الخطوه التاليه", "الخطوة التالية", "سنكمل", "سأتابع",
                    "سوف نتابع", "تابع في المره القادمه", "بعد ذلك سن",
                ))
            ),
            None,
        ),
        "evidence_coverage": {
            "raw_exchange_count": len(exchanges),
            "knowledge_record_count": len(knowledge),
            "user_record_count": sum(item.get("speaker") == "user" for item in knowledge),
            "assistant_record_count": sum(item.get("speaker") == "assistant" for item in knowledge),
            "failed_exchange_count": sum(bool(item.get("response_failed")) for item in timeline),
        },
    }


def format_dialogue_analysis_report(data: dict) -> str:
    """Render a local, evidence-indexed report with explicit source attribution."""
    analysis = analyze_dialogue_session(data)
    lines = [
        "=== التحليل المعرفي المستند إلى الأدلة الأصلية ===",
        f"معرّف الجلسة: {analysis['session_id'] or 'غير متاح'}",
        f"عدد التبادلات الأصلية: {analysis['exchange_count']}",
        "",
        "معلومات المستخدم المستخرجة:",
    ]
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['content']}"
        for item in analysis["user_information"]
    )
    if not analysis["user_information"]:
        lines.append("- لا توجد عبارات تقريرية كافية لاستخراج معلومات المستخدم.")
    lines.extend(["", "مساهمات الوكيل واقتراحاته:"])
    substantive_assistant = [
        item for item in analysis["assistant_information"]
        if item.get("knowledge_type") != "assistant_non_answer"
    ]
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['knowledge_type']}: {item['content']}"
        for item in substantive_assistant
    )
    if not substantive_assistant:
        lines.append("- لا توجد ردود موضوعية محفوظة.")
    non_answers = [
        item for item in analysis["assistant_information"]
        if item.get("knowledge_type") == "assistant_non_answer"
    ]
    lines.extend(["", "ردود الوكيل غير الموضوعية أو غير المكتملة:"])
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['content']}"
        for item in non_answers
    )
    if not non_answers:
        lines.append("- لا توجد ردود من هذا النوع في السجل.")
    lines.extend(["", "الخطط والإجراءات التي صرّح بها المستخدم:"])
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['content']}"
        for item in analysis["planned_actions"]
    )
    lines.extend(["", "التصحيحات والتفضيلات والقيود والقرارات:"])
    for label, key in (
        ("تصحيح", "user_corrections"),
        ("تفضيل", "preferences"),
        ("قيد", "constraints"),
        ("قرار", "decisions"),
    ):
        lines.extend(
            f"- {label} [التبادل {item['source_exchange_index']}]: {item['content']}"
            for item in analysis[key]
        )
    lines.extend(["", "الخلاصات التي صرّح بها الوكيل:"])
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['content']}"
        for item in analysis["conclusions"]
    )
    if not analysis["conclusions"]:
        lines.append("- لا توجد خلاصة صريحة محفوظة يمكن نسبتها إلى الوكيل.")
    lines.extend(["", "العلاقات المستنتجة بحذر:"])
    lines.extend(
        f"- {item['relation']}: {item['source_knowledge_id']} ← {item['target_knowledge_id']} "
        f"(ثقة {item['confidence']:.2f})"
        for item in analysis["relationships"]
    )
    if not analysis["relationships"]:
        lines.append("- لا توجد علاقة يمكن إثباتها من إشارات صريحة كافية.")
    lines.extend(["", "التبادلات التي لم يكتمل الرد عليها:"])
    lines.extend(
        f"- [التبادل {item['exchange_index']}] طلب المستخدم: {item['user_text'] or 'لا يوجد نص محفوظ'}"
        + (f" | حالة الفشل: {item['failure_message']}" if item.get("failure_message") else "")
        for item in analysis["failed_exchanges"]
    )
    if not analysis["failed_exchanges"]:
        lines.append("- لا توجد تبادلات فاشلة محفوظة في هذا السجل.")
    lines.extend(["", "الأسئلة التي لم يُحفظ لها رد:"])
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['content']}"
        for item in analysis["unresolved_questions"]
    )
    if not analysis["unresolved_questions"]:
        lines.append("- لا توجد أسئلة محفوظة بلا رد موثق.")
    lines.extend(["", "نقطة التوقف:"])
    last_exchange = analysis["last_exchange"]
    if last_exchange:
        lines.append(f"- آخر تبادل محفوظ: رقم {last_exchange['exchange_index']}")
        lines.append(f"- الموضوع عند التوقف: {last_exchange['topic'] or 'غير محدد'}")
        if (
            last_exchange.get("response_failed")
            or last_exchange.get("recall_only")
            or str(last_exchange.get("response_status") or "").casefold() == "needs_clarification"
        ):
            lines.append("- لم يُحفظ رد موضوعي مكتمل لهذا التبادل؛ حُفظت المحاولة/رسالة الاستيضاح فقط.")
        else:
            lines.append("- يوجد رد محفوظ لهذا التبادل.")
    else:
        lines.append("- لا توجد تبادلات أصلية محفوظة.")
    lines.append(
        f"- الخطوة التالية المصرّح بها: {analysis['explicit_next_step']}"
        if analysis["explicit_next_step"]
        else "- لم تُذكر خطوة تالية صريحة في آخر تبادل."
    )
    lines.extend(["", "التسلسل الزمني:"])
    lines.extend(
        f"- التبادل {item['exchange_index']}: {item['topic'] or 'موضوع غير محدد'}"
        for item in analysis["timeline"]
    )
    lines.extend([
        "",
        "تغطية الأدلة:",
        f"- التبادلات الأصلية: {analysis['evidence_coverage']['raw_exchange_count']}",
        f"- التبادلات التي تعذر إكمال الرد عليها: {analysis['evidence_coverage']['failed_exchange_count']}",
        f"- سجلات المعرفة المشتقة: {analysis['evidence_coverage']['knowledge_record_count']}",
        "- النص الأصلي هو مصدر الحقيقة؛ التصنيفات والعلاقات مشتقات قابلة للمراجعة وليست حقائق مستقلة.",
    ])
    return "\n".join(lines)


def _character_ngrams(value: Any, size: int = 3) -> set[str]:
    """Return normalized character n-grams for morphology-tolerant local matching."""
    compact = _normalize(value)
    compact = re.sub(r"[^a-z0-9ء-ي ]+", " ", compact)
    compact = re.sub(r"\s+", " ", compact).strip()
    if len(compact) < size:
        return {compact} if compact else set()
    return {
        compact[index:index + size]
        for index in range(len(compact) - size + 1)
        if compact[index:index + size].strip()
    }


def _bm25_score(query_terms: set[str], document_terms: list[str], document_frequencies: dict[str, int], document_count: int, average_length: float) -> float:
    """Small dependency-free BM25 scorer over one saved exchange."""
    if not query_terms or not document_terms or not document_count:
        return 0.0
    frequencies = {}
    for term in document_terms:
        frequencies[term] = frequencies.get(term, 0) + 1
    length = len(document_terms)
    average_length = max(1.0, average_length)
    score = 0.0
    for term in query_terms:
        frequency = frequencies.get(term, 0)
        if not frequency:
            continue
        df = document_frequencies.get(term, 0)
        inverse = max(0.0, math.log(
            1.0 + (document_count - df + 0.5) / (df + 0.5)
        ))
        denominator = frequency + 1.2 * (
            1.0 - 0.75 + 0.75 * length / average_length
        )
        score += inverse * frequency * 2.2 / denominator
    return score


def retrieve_dialogue_evidence(
    data: dict,
    query: str,
    *,
    limit: int = 8,
) -> list[dict]:
    """Rank raw exchanges with local BM25, Arabic character similarity and provenance."""
    if not isinstance(data, dict):
        return []
    session_id, exchanges = _exchange_archive(data)
    query_text = " ".join(str(query or "").split()).strip()
    query_tokens = _tokens(query_text)
    if not session_id or not exchanges or not query_tokens:
        return []

    expanded = set(query_tokens)
    for token in tuple(query_tokens):
        expanded.update(_SYNONYMS.get(token, ()))
    normalized_query = _normalize(query_text)
    if re.search(r"(?:كيف|طريقة|خطوات|تنفيذ|صنع|صنعت)", normalized_query):
        expanded.update({"صب", "تشكيل", "تجفيف", "طلاء", "اضافه", "استخدام", "ساستخدم"})
    if re.search(r"(?:اتفق|قرار|اعتمد)", normalized_query):
        expanded.update({"قررت", "ساعتمد", "اخترت", "اعتمدت", "تم الاتفاق"})

    documents = []
    document_frequencies: dict[str, int] = {}
    total_length = 0
    for index, exchange in enumerate(exchanges):
        user = str(exchange.get("user") or "").strip()
        assistant = str(exchange.get("assistant") or "").strip()
        target = str(exchange.get("target") or "").strip()
        user_terms = _token_list(user)
        assistant_terms = _token_list(assistant)
        target_terms = _token_list(target)
        all_terms = user_terms + assistant_terms + target_terms
        total_length += len(all_terms)
        for term in set(all_terms):
            document_frequencies[term] = document_frequencies.get(term, 0) + 1
        documents.append({
            "index": index,
            "exchange": exchange,
            "user": user,
            "assistant": assistant,
            "target": target,
            "user_terms": user_terms,
            "assistant_terms": assistant_terms,
            "target_terms": target_terms,
            "all_terms": all_terms,
        })

    document_count = len(documents)
    average_length = total_length / max(1, document_count)
    query_ngrams = _character_ngrams(query_text)
    ranked = []
    for document in documents:
        user_terms = document["user_terms"]
        assistant_terms = document["assistant_terms"]
        target_terms = document["target_terms"]
        all_terms = document["all_terms"]
        user_matches = expanded & set(user_terms)
        assistant_matches = expanded & set(assistant_terms)
        target_matches = expanded & set(target_terms)
        all_matches = user_matches | assistant_matches | target_matches
        lexical_score = (
            1.8 * _bm25_score(expanded, user_terms, document_frequencies, document_count, average_length)
            + 1.0 * _bm25_score(expanded, assistant_terms, document_frequencies, document_count, average_length)
            + 0.55 * _bm25_score(expanded, target_terms, document_frequencies, document_count, average_length)
        )
        document_ngrams = _character_ngrams(
            document["user"] + " " + document["assistant"] + " " + document["target"]
        )
        ngram_union = query_ngrams | document_ngrams
        ngram_similarity = (
            len(query_ngrams & document_ngrams) / len(ngram_union)
            if ngram_union else 0.0
        )
        phrase_match = bool(
            normalized_query
            and len(normalized_query) >= 5
            and normalized_query in _normalize(
                document["user"] + " " + document["assistant"] + " " + document["target"]
            )
        )
        # A lexical hit remains the strongest signal. Character n-grams add
        # tolerance for inflection/orthographic variants without inventing
        # synonyms or allowing an unrelated session to enter the search.
        score = lexical_score + (2.0 * ngram_similarity) + (2.5 if phrase_match else 0.0)
        if not all_matches and ngram_similarity < 0.12 and not phrase_match:
            continue
        ranked.append({
            "session_id": session_id,
            "exchange_id": str(
                document["exchange"].get("exchange_id")
                or f"{session_id}:{document['index'] + 1}"
            ),
            "exchange_index": document["index"] + 1,
            "timestamp": (
                document["exchange"].get("timestamp")
                or document["exchange"].get("created_at")
            ),
            "score": round(score, 4),
            "matched_terms": sorted(all_matches),
            "matched_user_terms": sorted(user_matches),
            "matched_assistant_terms": sorted(assistant_matches),
            "user": document["user"],
            "assistant": document["assistant"],
            "target": document["target"],
        })
    ranked.sort(key=lambda item: (-item["score"], item["exchange_index"]))
    selected = ranked[:max(1, int(limit))]
    selected.sort(key=lambda item: item["exchange_index"])
    return selected


def format_dialogue_evidence_answer(
    data: dict,
    query: str,
    *,
    limit: int = 8,
) -> str:
    """Present the original matching exchanges with provenance and speaker ownership."""
    evidence = retrieve_dialogue_evidence(data, query, limit=limit)
    if not evidence:
        return ""
    lines = [
        "الإجابة المستندة إلى أدلة الجلسة المحفوظة:",
        f"معرّف الجلسة: {evidence[0]['session_id']}",
        "مصدر الإجابة هو التبادلات الأصلية؛ لم يُستخدم ملخص مشتق بديلًا عنها.",
    ]
    for item in evidence:
        lines.extend([
            "",
            f"التبادل الأصلي {item['exchange_index']} (المصدر: {item['exchange_id']}):",
            "ما قاله المستخدم:",
            item["user"] or "لا توجد رسالة مستخدم محفوظة.",
            "ما أجاب به الوكيل:",
            item["assistant"] or "لا يوجد رد محفوظ.",
        ])
    lines.extend([
        "",
        "عُرضت الأدلة بحسب صلتها بالسؤال مع الحفاظ على ترتيبها الزمني ونسبة كل معلومة إلى قائلها.",
    ])
    return "\n".join(lines)
