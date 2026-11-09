"""Evidence-grounded retrieval for saved dialogue sessions.

This module returns source exchanges rather than unsupported semantic answers.
It is local-only, deterministic, and preserves speaker attribution.
"""
from __future__ import annotations

import re
from typing import Any


_STOP_WORDS = {
    "ما", "ماذا", "من", "هل", "كيف", "اين", "متى", "كم", "اي", "هي", "هو",
    "الذي", "التي", "في", "عن", "على", "الى", "مع", "بين", "لك", "لي", "لنا",
    "انا", "انت", "انتم", "هذا", "هذه", "ذلك", "تلك", "كان", "كانت", "تم",
    "قد", "ثم", "او", "الجلسة", "جلسة", "المحفوظة", "المحفوظ", "رقم",
    "اذكر", "حدد", "ذكرت", "ذكرته", "ذكرتها", "قلته", "قلتها", "قلت", "كنا",
}
import hashlib as _hashlib


def _exchange_source_fingerprint(exchange: dict) -> str:
    raw = "\0".join((str(exchange.get("user") or ""), str(exchange.get("assistant") or "")))
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()


_SYNONYMS = {
    "ادوات": {"سكين", "مفك", "براغي", "ملعقة", "معدات", "اداة"},
    "اداة": {"سكين", "مفك", "براغي", "ملعقة", "معدات"},
    "سماكه": {"سم", "جبس", "سماكة", "سمك"},
    "سماكة": {"سم", "جبس", "سماكه", "سمك"},
    "الوان": {"ذهبي", "ذهبية", "ابيض", "ازرق"},
    "لون": {"ذهبي", "ذهبية", "ابيض", "ازرق"},
    "طلاء": {"صباغة", "صباغه", "اسود", "دهان"},
    "صباغه": {"طلاء", "اسود", "دهان"},
    "حمايه": {"كولا", "ورنيش", "طبقة", "شفاف"},
    "حماية": {"كولا", "ورنيش", "طبقة", "شفاف"},
}


def _normalize(value: Any) -> str:
    text = str(value or "").casefold()
    text = (text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ى", "ي").replace("ـ", ""))
    return re.sub(r"[\u064b-\u065f\u0670]", "", text)


def _tokens(value: Any) -> set[str]:
    result = set()
    for token in re.findall(r"[a-z0-9]+|[\u0621-\u064a]+", _normalize(value)):
        if len(token) > 4 and token.startswith("وال"):
            token = token[3:]
        elif len(token) > 4 and token.startswith(("بال", "لل")):
            token = token[2:]
        elif len(token) > 3 and token.startswith("ال"):
            token = token[2:]
        elif len(token) > 3 and token.startswith(("و", "ب", "ل")):
            token = token[1:]
        if len(token) > 3 and token.endswith(("ها", "هم", "كم")):
            token = token[:-2]
        if token and token not in _STOP_WORDS and not token.isdigit():
            result.add(token)
    return result


def _exchange_archive(data: dict) -> tuple[str, list[dict]]:
    dialogue = data.get("dialogue_state")
    if not isinstance(dialogue, dict):
        return "", []
    record_session_id = str(data.get("session_id") or "").strip()
    dialogue_session_id = str(dialogue.get("session_id") or "").strip()
    if record_session_id and dialogue_session_id and record_session_id != dialogue_session_id:
        # A nested transcript from another session must never be attributed to
        # the outer record merely because it was found in the selected file.
        return "", []
    session_id = record_session_id or dialogue_session_id
    if not session_id:
        return "", []
    records = []
    for item in dialogue.get("exchange_archive") or []:
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
    return session_id, records


def retrieve_dialogue_evidence(data: dict, query: str, *, limit: int = 5) -> list[dict]:
    """Rank exact saved exchanges for a new question, retaining original speakers."""
    if not isinstance(data, dict):
        return []
    session_id, exchanges = _exchange_archive(data)
    query_tokens = _tokens(query)
    if not session_id or not exchanges or not query_tokens:
        return []
    expanded = set(query_tokens)
    for token in tuple(query_tokens):
        expanded.update(_SYNONYMS.get(token, ()))
    ranked = []
    for index, exchange in enumerate(exchanges):
        user = str(exchange.get("user") or "").strip()
        assistant = str(exchange.get("assistant") or "").strip()
        target = str(exchange.get("target") or "").strip()
        user_tokens = _tokens(user + " " + target)
        assistant_tokens = _tokens(assistant)
        matched = expanded & (user_tokens | assistant_tokens)
        if not matched:
            continue
        score = len(matched) / max(1.0, len(expanded) ** 0.5)
        score += 0.20 * len(expanded & user_tokens)
        ranked.append({
            "session_id": session_id,
            "exchange_index": index + 1,
            "score": round(score, 4),
            "matched_terms": sorted(matched),
            "user": user,
            "assistant": assistant,
            "target": target,
        })
    ranked.sort(key=lambda item: (-item["score"], item["exchange_index"]))
    selected = ranked[:max(1, int(limit))]
    selected.sort(key=lambda item: item["exchange_index"])
    return selected


def format_dialogue_evidence_answer(data: dict, query: str, *, limit: int = 5) -> str:
    """Render retrieved evidence with provenance; do not fabricate a synthesis."""
    evidence = retrieve_dialogue_evidence(data, query, limit=limit)
    if not evidence:
        return ""
    dialogue = data.get("dialogue_state")
    session_id = str(data.get("session_id") or "").strip()
    if isinstance(dialogue, dict):
        session_id = str(dialogue.get("session_id") or session_id).strip()
    lines = [
        "المعلومات الموثقة ذات الصلة في الجلسة المحفوظة:",
        f"معرّف الجلسة: {session_id}",
        "هذه مقتطفات من التبادلات الأصلية؛ جرى الحفاظ على نسبة كل رسالة إلى صاحبها.",
    ]
    for item in evidence:
        lines.extend([
            "",
            f"التبادل الأصلي رقم {item['exchange_index']}:",
            "رسالة المستخدم:",
            item["user"] or "لا توجد رسالة مستخدم محفوظة.",
            "رد الوكيل:",
            item["assistant"] or "لا يوجد رد محفوظ.",
        ])
    lines.extend([
        "",
        "هذه أدلة مسترجعة وليست استنتاجًا جديدًا؛ يجب بناء أي تفسير إضافي منها دون إضافة معلومات غير مسجلة.",
    ])
    return "\n".join(lines)


# Structured, source-attributed knowledge derived from the immutable exchange archive.
# Existing sessions without these fields are analyzed on demand; no migration is needed.
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
    if any(marker in normalized for marker in (
        "ساستخدم", "ساضيف", "ساقوم", "ساضع", "سوف استخدم",
        "سوف اضع", "سوف اترك", "سأقوم",
    )):
        return "planned_action", 0.70
    if any(marker in normalized for marker in (
        "قررت", "ساعتمد", "اخترت", "اعتمدت", "تم الاتفاق",
    )):
        return "decision", 0.78
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
        return "", []
    record_session_id = str(data.get("session_id") or "").strip()
    dialogue_session_id = str(dialogue.get("session_id") or "").strip()
    if record_session_id and dialogue_session_id and record_session_id != dialogue_session_id:
        return "", []
    session_id = record_session_id or dialogue_session_id
    if not session_id:
        return "", []
    records = []
    for archive_name in ("exchange_archive", "failed_exchange_archive"):
        for item in dialogue.get(archive_name) or []:
            if not isinstance(item, dict) or item.get("state_boundary_only"):
                continue
            item_session_id = str(item.get("session_id") or "").strip()
            if item_session_id and item_session_id != session_id:
                continue
            if archive_name == "failed_exchange_archive" and not item.get("response_failed"):
                continue
            if not (
                str(item.get("user") or "").strip()
                or str(item.get("assistant") or "").strip()
                or item.get("response_failed")
            ):
                continue
            records.append(item)
    records.sort(key=lambda item: (
        str(item.get("timestamp") or item.get("created_at") or ""),
        str(item.get("exchange_id") or ""),
    ))
    return session_id, records

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
    failure_markers = (
        "لم افهم", "لا املك سجل", "تعذر توليد", "تعذر الوصول",
        "provider_exception", "لا توجد ادله كافيه", "لم استطع",
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
            "failure_message": str(exchange.get("failure_message") or ""),
        })

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
            if kind in {"user_fact", "decision", "preference", "constraint"}:
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
                has_answer = bool(assistant_text.strip()) and not any(
                    marker in normalized_answer for marker in failure_markers
                ) and not exchange.get("response_failed")
                if not has_answer:
                    unresolved.append(item)

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
        "questions": [
            item for item in knowledge if item.get("knowledge_type") == "question"
        ],
        "unresolved_questions": unresolved,
        "failed_exchanges": [
            item for item in timeline if item.get("response_failed")
        ],
        "relationships": relationships,
        "last_exchange": timeline[-1] if timeline else None,
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
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['knowledge_type']}: {item['content']}"
        for item in analysis["assistant_information"]
    )
    if not analysis["assistant_information"]:
        lines.append("- لا توجد ردود موضوعية محفوظة.")
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
    lines.extend(["", "الأسئلة غير المحسومة:"])
    lines.extend(
        f"- [التبادل {item['source_exchange_index']}] {item['content']}"
        for item in analysis["unresolved_questions"]
    )
    if not analysis["unresolved_questions"]:
        lines.append("- لا توجد أسئلة محفوظة بلا رد موثق.")
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


def retrieve_dialogue_evidence(
    data: dict,
    query: str,
    *,
    limit: int = 8,
) -> list[dict]:
    """Rank evidence across the selected session with speaker-aware relevance."""
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

    ranked = []
    for index, exchange in enumerate(exchanges):
        user = str(exchange.get("user") or "").strip()
        assistant = str(exchange.get("assistant") or "").strip()
        target = str(exchange.get("target") or "").strip()
        user_tokens = _tokens(user)
        assistant_tokens = _tokens(assistant)
        target_tokens = _tokens(target)
        user_matches = expanded & user_tokens
        assistant_matches = expanded & assistant_tokens
        target_matches = expanded & target_tokens
        all_matches = user_matches | assistant_matches | target_matches
        phrase_match = bool(
            normalized_query
            and len(normalized_query) >= 5
            and normalized_query in _normalize(user + " " + assistant + " " + target)
        )
        if not all_matches and not phrase_match:
            continue
        score = (
            2.4 * len(user_matches)
            + 1.2 * len(assistant_matches)
            + 0.8 * len(target_matches)
            + (3.0 if phrase_match else 0.0)
        ) / max(1.0, len(expanded) ** 0.5)
        ranked.append({
            "session_id": session_id,
            "exchange_id": str(exchange.get("exchange_id") or f"{session_id}:{index + 1}"),
            "exchange_index": index + 1,
            "timestamp": exchange.get("timestamp") or exchange.get("created_at"),
            "score": round(score, 4),
            "matched_terms": sorted(all_matches),
            "matched_user_terms": sorted(user_matches),
            "matched_assistant_terms": sorted(assistant_matches),
            "user": user,
            "assistant": assistant,
            "target": target,
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
