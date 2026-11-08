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
