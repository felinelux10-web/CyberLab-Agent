# CyberLab Agent v4.8
# memory/session_state.py

import json
import os
import re
import uuid
from datetime import datetime

def _session_file() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("session_state.json")


MAX_RECENT_SESSIONS = 5
MAX_SESSION_INDEX = 100
SESSION_SCHEMA_VERSION = 2


def _archive_file() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("session_archive.json")


def _append_recent_archive(data: dict) -> None:
    """Keep a searchable compact index; never archive the transcript here."""
    path = _archive_file()
    try:
        with open(path, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = []
    if not isinstance(archive, list):
        archive = []
    summary = {key: data.get(key)
        for key in (
            "schema_version", "session_id", "created_at", "updated_at", "timestamp", "title",
            "session_type", "status", "project", "summary", "topic", "current_state",
            "active_goal", "completed_work", "confirmed_achievements", "last_completed_step",
            "pending_tasks", "next_step", "last_files", "relevant_files", "decisions",
            "open_questions", "project_root", "last_updated",
        )
        if key in data
    }
    # Session numbers are positional references shown to the user. Updating a
    # session must not move it to a new position, or the same number can select
    # a different dialogue immediately after a successful restore.
    session_id = str(summary.get("session_id") or "").strip()
    normalized = []
    positions = {}
    for item in archive:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("session_id") or "").strip()
        if not item_id:
            continue
        if item_id in positions:
            # Legacy archives may already contain duplicate IDs. Keep the
            # first position, but refresh its metadata from the latest record.
            position = positions[item_id]
            normalized[position] = {**normalized[position], **item}
        else:
            positions[item_id] = len(normalized)
            normalized.append(item)
    archive = normalized
    if session_id:
        if session_id in positions:
            position = positions[session_id]
            archive[position] = {**archive[position], **summary}
        else:
            archive.append(summary)
    archive = archive[-MAX_SESSION_INDEX:]
    # The archive is the durable searchable index. The UI helper below still
    # returns only a small recent window for mobile/Termux memory limits.
    from lab_v4_dev.memory.intelligence import atomic_write_json
    atomic_write_json(path, archive)


def _session_updated_key(item: dict) -> str:
    return str(item.get("updated_at") or item.get("timestamp") or item.get("created_at") or "")


def get_recent_sessions() -> list:
    """Return the most recently updated unique sessions, newest first."""
    return sorted(
        get_session_index(),
        key=_session_updated_key,
        reverse=True,
    )[:MAX_RECENT_SESSIONS]


def get_session_index() -> list:
    """Load a unique, position-stable session index without transcripts.

    The stored order is the numbering contract used by list and restore
    commands. Deduplicate legacy repeated IDs in place; refresh metadata from
    later copies without moving the session's original position.
    """
    try:
        with open(_archive_file(), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        result = []
        positions = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("session_id") or "").strip()
            if not session_id:
                continue
            if session_id in positions:
                position = positions[session_id]
                result[position] = {**result[position], **item}
            else:
                positions[session_id] = len(result)
                result.append(item)
        return result[-MAX_SESSION_INDEX:]
    except Exception:
        return []


def _details_dir() -> str:
    from lab_v4_dev.core.project_context import project_data_dir
    return os.path.join(project_data_dir(), "sessions")


def _detail_file(session_id: str) -> str:
    safe_id = "".join(ch for ch in str(session_id or "") if ch.isalnum() or ch in "_-." )
    return os.path.join(_details_dir(), f"{safe_id}.json")


def _write_session_detail(data: dict) -> None:
    session_id = str(data.get("session_id") or "").strip()
    if not session_id:
        return
    path = _detail_file(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    from lab_v4_dev.memory.intelligence import atomic_write_json
    atomic_write_json(path, data)


def _load_session_detail(session_id: str) -> dict:
    path = _detail_file(session_id)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _session_text(item: dict) -> str:
    fields = (
        "title", "project", "session_type", "status", "topic", "current_state",
        "active_goal", "next_step", "completed_work", "confirmed_achievements",
        "decisions", "open_questions",
    )
    return " ".join(str(item.get(field, "")) for field in fields).casefold()


def search_sessions(query: str = "", *, status: str | None = None,
                    project: str | None = None, limit: int = 10) -> list:
    """Search the full saved-session index, then rank by content relevance."""
    from lab_v4_dev.memory.intelligence import rank_memory_records
    needle = str(query or "").strip()
    candidates = []
    for item in get_session_index():
        if status and str(item.get("status", "")).casefold() != str(status).casefold():
            continue
        if project and str(project).casefold() not in _session_text(item).casefold():
            continue
        candidates.append(item)
    if not needle:
        return sorted(candidates, key=_session_updated_key, reverse=True)[:max(1, int(limit))]
    return rank_memory_records(
        needle, candidates,
        fields=("title","project","topic","active_goal","summary","current_state","next_step",
                "confirmed_achievements","completed_work","decisions","open_questions"),
        minimum_score=0.12, limit=max(1, int(limit)),
    )


def get_session_by_id(session_id: str) -> dict:
    """Resolve one saved session by exact identity; reject mismatched detail payloads."""
    wanted = str(session_id or "").strip()
    if not wanted:
        return {}
    current = load_session()
    if isinstance(current, dict) and str(current.get("session_id") or "").strip() == wanted:
        return current

    # A detail file is named by session ID, but legacy/corrupt files can contain
    # a different embedded ID. The filename alone is not proof of identity.
    detail = _load_session_detail(wanted)
    if (
        isinstance(detail, dict)
        and str(detail.get("session_id") or "").strip() == wanted
    ):
        return detail

    # Fall back only to the matching compact index entry, never to a mismatched
    # detail record or the current session.
    for item in get_session_index():
        if isinstance(item, dict) and str(item.get("session_id") or "").strip() == wanted:
            return item
    return {}


def get_session_by_number(number: int) -> dict:
    """Resolve the stable user-visible session number to one exact indexed record."""
    try:
        number = int(number)
    except (TypeError, ValueError, OverflowError):
        return {}
    if number < 1:
        return {}

    # Use the same stable index and 1-based numbering contract as the startup UI.
    index = get_session_index()
    if number > len(index):
        return {}
    selected = index[number - 1]
    if not isinstance(selected, dict):
        return {}
    session_id = str(selected.get("session_id") or "").strip()
    if not session_id:
        return {}

    # Resolve by identity and verify the returned record. Never silently fall
    # back to load_session() or a different session if detail/index data disagree.
    resolved = get_session_by_id(session_id)
    if not isinstance(resolved, dict):
        return {}
    if str(resolved.get("session_id") or "").strip() != session_id:
        return {}
    return resolved


def get_latest_session_by_type(session_type: str) -> dict:
    """Return the newest persisted session of exactly the requested type."""
    wanted = str(session_type or "").strip().casefold()
    if not wanted:
        return {}
    for item in sorted(get_session_index(), key=_session_updated_key, reverse=True):
        if str(item.get("session_type") or "").casefold() != wanted:
            continue
        selected = get_session_by_id(item.get("session_id"))
        return selected or item
    current = load_session()
    if isinstance(current, dict) and str(current.get("session_type") or "").casefold() == wanted:
        return current
    return {}


def session_selector(raw: str) -> dict:
    """Classify explicit session selection/report language without an LLM."""
    raw_text = str(raw or "").strip()
    text = raw_text.casefold()
    # Normalize common Arabic typing variants for matching only. Preserve raw_text.
    text = (
        text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        .replace("ى", "ي").replace("ـ", "")
        .replace("ملهص", "ملخص").replace("نلخص", "ملخص")
        .replace("مظمون", "مضمون")
        .replace("جنيع", "جميع").replace("جميغ", "جميع")
    )
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    # Repair common mobile/terminal input where adjacent words are joined.
    text = re.sub(r"(?<=ماذا)(?=كنا\b)", " ", text)
    text = re.sub(r"(?<=ما)(?=كنا\b)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Multi-session summaries must be routed to the saved-session store,
    # not the runtime SESSION_REPORT handler.
    collective_sessions = re.search(
        r"(?<!\w)(?:لجميع|لكل|لل|لكافة|كافة|جميع|كل)\s*(?:(?:ال)?جلس(?:ة|ات|ه))(?!\w)",
        text,
    )
    asks_for_summary = any(
        marker in text
        for marker in ("ملخص", "تلخيص", "لخص", "مضمون", "محتوى", "المحتوى", "المضمون")
    )
    # Requests specifically about work sessions must not be interpreted as a
    # technical question about session hijacking or as a mixed-session report.
    work_sessions_mentioned = bool(re.search(
        r"(?:جلسات|الجلسات)\s+(?:العمل|العملية|العمليات)",
        text,
    ))
    if work_sessions_mentioned and asks_for_summary:
        return {
            "kind": "list",
            "session_type": "work",
            "report_mode": "summaries",
        }
    sessions_with_all_suffix = re.search(
        r"(?:الجلسات|جلسات)(?:\s+(?:المحفوظة|السابقة|القديمة))?\s+(?:كلها|جميعها|كافه)",
        text,
    )
    if (collective_sessions or sessions_with_all_suffix) and asks_for_summary:
        return {"kind": "list", "report_mode": "summaries"}

    # A deictic request is not a safe selector for the latest saved checkpoint.
    if asks_for_summary and any(marker in text for marker in (
        "هذه الجلسة", "هذه الجلسه", "هذه الجلسات",
        "الجلسة التي عرضتها", "الجلسه التي عرضتها",
        "الجلسة التي عرضتها انت", "الجلسه التي عرضتها انت",
    )):
        return {"kind": "reference", "report_mode": "standard"}

    report_mode = "standard"
    if any(token in text for token in (
        "نص الحوار حرفيا", "نص الحوار حرفيًا", "الحوار المحفوظ حرفيا",
        "الحوار المحفوظ حرفيًا", "اعرض الرسائل الأصلية", "اعرض نص الحوار",
        "سجل الحوار حرفيا", "سجل الحوار حرفيًا",
    )):
        report_mode = "transcript"
    elif any(token in text for token in ("فقط", "المعرف والحالة", "المعرّف والموضوع والحالة")):
        report_mode = "compact"
    elif any(token in text for token in ("أين توقفنا", "اين توقفنا", "الخطوة التالية", "ما الذي أُنجز", "ما الذي انجز")):
        report_mode = "progress"
    elif any(token in text for token in (
        "ملخصات كل الجلسات", "ملخصات جميع الجلسات", "ملخصات الجلسات",
        "ملخصات كل الجلسات المحفوظة", "ملخصات جميع الجلسات المحفوظة",
        "ملخص عن كل الجلسات", "ملخص لكل الجلسات", "لخص كل الجلسات",
        "لخص جميع الجلسات", "ملخصات الجلسات المحفوظة",
        "كل الجلسات وملخصاتها", "جميع الجلسات وملخصاتها",
        "كل الجلسات المحفوظة وملخصاتها", "الجلسات المحفوظة وملخصاتها",
        "اعرض الجلسات مع ملخصاتها", "اعرض كل الجلسات مع ملخصاتها",
        "اعرض جميع الجلسات مع ملخصاتها",
        "اكتب ملخصات الجلسات المحفوظة كلها", "اكتب ملخصات كل الجلسات المحفوظة",
        "ملخصات الجلسات السابقة كلها", "ملخصات الجلسات المحفوظة كلها",
        "نلخصات الجلسات السابقة كلها", "نلخصات الجلسات المحفوظة كلها",
        "اعرض نلخصات الجلسات", "اعرض نلخصات الجلسات السابقة",
        "اعرض ملخصات الجلسة المحفوظة",
    )):
        report_mode = "summaries"
    elif any(token in text for token in (
        "تقرير كامل", "تقريرًا كاملًا", "تقريرا كاملا",
        "اكتب ملخص الجلسة المحفوظة", "اكتب تقرير الجلسة المحفوظة",
        "تقرير الجلسة المحفوظة", "ملخص الجلسة المحفوظة",
    )):
        report_mode = "full"
    id_match = re.search(r"(?:معرّف|معرف|id)\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9_.-]{5,})", raw_text, flags=re.IGNORECASE)
    if id_match and any(token in text for token in ("جلسة", "استعد", "استرجع", "ابحث")):
        return {"kind": "id", "session_id": id_match.group(1), "report_mode": report_mode}
    count_request = any(token in text for token in (
        "كم عدد الجلسات", "عدد الجلسات", "كم جلسة محفوظة",
        "كم عدد الجلسات المحفوظة", "عدد الجلسات المحفوظة",
        "كم عدد الجلسات السابقة", "عدد الجلسات السابقة",
    ))
    if count_request and any(token in text for token in ("جلسة", "جلسات", "الجلسات")):
        return {"kind": "count", "report_mode": "compact"}
    # Resolve an explicit session number before broad latest-session fallbacks.
    # Allow descriptive words between "session" and its number, e.g.
    # "ملخص الجلسة المحفوظة رقم 30"; otherwise the request silently selects latest.
    number_match = re.search(
        r"(?<!\w)(?:الجلسة|الجلسه|جلسة|جلسه|session)"
        r"(?:\s+(?:(?!رقم\b)[\w-]+)){0,5}\s*(?:رقم\s*)?#?\s*(\d+)\b",
        text,
        flags=re.IGNORECASE,
    )
    if number_match and any(token in text for token in (
        "استرجع", "استعد", "استكمل", "استكمال", "اعرض", "اكتب", "اقرا", "حلل",
        "ملخص", "تلخيص", "لخص", "مضمون", "محتوى", "تقرير", "ما الموضوع",
        "ماذا كنا", "ما كنا", "ما الفرق", "restore", "resume", "summarize",
        "summary", "report",
    )):
        return {
            "kind": "number",
            "number": int(number_match.group(1)),
            "report_mode": report_mode,
        }
    if any(token in text for token in ("الجلسات المعلقة", "جلسات معلقة", "المهام المعلقة")):
        return {"kind": "status", "status": "paused", "report_mode": report_mode}
    if "قارن" in text and any(token in text for token in ("الجلسات", "جلستين", "جلسة")):
        return {"kind": "compare", "report_mode": "full"}
    # A question about the content/topic of a temporally referenced session
    # denotes saved-dialogue recall, not the generic latest-work checkpoint.
    # Use the relationship between a prior-session reference and a content
    # question rather than requiring one exact sentence template.
    prior_session_content_reference = bool(
        re.search(
            r"(?:الجلسة|الجلسه|جلسة|جلسه|الجلسات|جلسات)"
            r"\s+(?:ال)?(?:سابقة|سابقه|سابق|ماضية|ماضيه|ماضي|اخيرة|اخيره|اخير)",
            text,
        )
        and (
            asks_for_summary
            or any(marker in text for marker in (
                "موضوع", "مضمون", "محتوى", "كنا نقول", "كنا نتحدث",
                "كنا نتكلم", "كنا نناقش", "ناقشنا", "تحدثنا",
                "نتحدث", "نتكلم", "نتناقش", "ماذا قلنا", "ما قلنا",
            ))
        )
    )
    # A request about the content (not just the inventory) of one saved
    # dialogue may omit a temporal adjective. Keep collection/list phrasing
    # out of this route: "ملخصات الجلسات المحفوظة كلها" is a list request.
    saved_dialogue_content_reference = bool(
        re.search(
            r"(?:الجلسة|الجلسه|جلسة|جلسه|الحوار|حوار|الدردشة|دردشة)"
            r"\s+(?:ال)?محفوظ(?:ة|ه|ات)?",
            text,
        )
        and any(marker in text for marker in (
            "موضوع", "مضمون", "محتوى", "كنا نقول", "كنا نتحدث",
            "كنا نتكلم", "كنا نناقش", "ناقشنا", "تحدثنا",
            "نتحدث", "نتكلم", "نتناقش", "ماذا قلنا", "ما قلنا",
        ))
    )
    if prior_session_content_reference or saved_dialogue_content_reference:
        # Explicit collection/list markers have precedence over single-dialogue recall.
        if not any(marker in text for marker in (
            "كلها", "جميعها", "كل الجلسات", "جميع الجلسات",
            "ملخصات الجلسات", "ملخصات كل الجلسات",
            "ملخصات جميع الجلسات", "الجلسات المحفوظة كلها",
        )):
            return {"kind": "previous_dialogue", "report_mode": report_mode}
    # A retrospective question explicitly anchored to "the last session"
    # is persisted-dialogue recall; the same wording without a session anchor
    # remains a live DialogueMemory request.
    last_session_dialogue_reference = bool(
        re.search(
            r"(?:اخر|آخر)\s+جلس(?:ة|ه)|(?:الجلسة|الجلسه)\s+(?:ال)?اخير(?:ة|ه)",
            text,
        )
        and any(marker in text for marker in (
            "ماذا كنا نقول", "كنا نقول", "ماذا كنا نتحدث",
            "كنا نتحدث", "كنا نتكلم", "كنا نناقش",
        ))
    )
    if last_session_dialogue_reference:
        return {"kind": "previous_dialogue", "report_mode": report_mode}

    # Distinguish a prior saved dialogue from the generic latest session/work report.
    # This is intentionally checked before broad "استرجع الجلسة" -> latest matching.
    previous_dialogue_markers = (
        "حوار الجلسة السابقة", "حوار الجلسه السابقه",
        "الجلسة السابقة المحفوظة", "الجلسه السابقه المحفوظه",
        "نص الحوار المحفوظ", "سجل الحوار المحفوظ", "الحوار المحفوظ",
        "موضوع الجلسة السابقة", "موضوعنا السابق",
        "سياق الجلسة السابقة", "سياق الجلسه السابقه",
        "عن اي موضوع كنا نتحدث في الجلسة المحفوظة",
        "عن أي موضوع كنا نتحدث في الجلسة المحفوظة",
        "الموضوع الذي ناقشناه سابقا", "الموضوع الذي ناقشناه سابقًا",
        "ما الموضوع الذي ناقشناه", "موضوع ناقشناه سابقا",
        "موضوع ناقشناه سابقًا", "الموضوع الذي تحدثنا عنه سابقا",
        "الموضوع الذي تحدثنا عنه سابقًا",
    )
    if any(token in text for token in previous_dialogue_markers) and any(
        token in text for token in ("حوار", "الحوار", "كنا", "موضوع", "نقاش", "نتحدث", "نقول", "سياق", "تقرير", "استرجع", "استرجاع", "تذكر", "تتذكر", "ملخص")
    ):
        return {"kind": "previous_dialogue", "report_mode": report_mode}
    if any(token in text for token in ("آخر جلسة", "اخر جلسة", "الجلسة الأخيرة", "الجلسه الاخيره")):
        return {"kind": "latest", "report_mode": report_mode}
    search_marker = re.search(r"(?:عن|حول)\s+(.*?)(?:،|,|\s+واعرض|\s+ثم|\s+فقط|$)", raw_text, flags=re.IGNORECASE)
    other_saved_topic = (
        any(marker in text for marker in (
            "جلسة اخرى", "جلسه اخرى", "جلسة اخري", "جلسه اخري", "جلسة أخرى", "جلسه أخرى",
            "جلسة مختلفة", "جلسه مختلفه", "حوار آخر", "حوار اخر",
        ))
        and any(marker in text for marker in (
            "كنا نتحدث", "كنا نتكلم", "كنا نناقش", "كنا نقول",
            "عن موضوع", "حول موضوع", "الفن", "الرسم", "النحت", "النقش",
        ))
    )
    if other_saved_topic:
        query = search_marker.group(1).strip() if search_marker else raw_text
        query = re.sub(r"^(?:موضوع|موضوع عن|الموضوع)\s+", "", query).strip()
        return {"kind": "search", "query": query, "report_mode": report_mode}
    if any(token in text for token in ("ابحث في الجلسات", "ابحث عن جلسة", "جلسة مشروع", "جلسه مشروع", "جلسة إصلاح", "جلسة اختبار", "جلسه اختبار", "جلسة التي", "جلسه التي")):
        query = search_marker.group(1).strip() if search_marker else raw_text
        query = re.sub(r"^(?:جلسة|الجلسة|جلسه|الجلسه)\s+", "", query, flags=re.IGNORECASE).strip()
        return {"kind": "search", "query": query, "report_mode": report_mode}
    list_markers = (
        "جميع الجلسات", "كل الجلسات", "الجلسات كلها", "جلساتنا كلها",
        "كل الجلسات المحفوظة", "جميع الجلسات المحفوظة",
        "الجلسات المحفوظة كلها", "ملخصات الجلسات", "ملخصات جميع الجلسات",
        "ملخصات كل الجلسات", "جميع الملخصات", "كل الملخصات",
        "ملخص عن كل الجلسات", "ملخص لكل الجلسات", "لخص كل الجلسات",
        "لخص جميع الجلسات", "ملخصات الجلسات المحفوظة",
        "اعرض الجلسات", "اعرض جميع الجلسات", "اعرض كل الجلسات",
        "اعرض ملخصات الجلسات", "اعرض ملخصات جميع الجلسات",
        "اعرض ملخصات كل الجلسات", "اعرض ملخصات كل الجلسات المحفوظة",
        "قائمة الجلسات المحفوظة", "الجلسات المحفوظة كلها",
        "كل الجلسات السابقة", "الجلسات السابقة كلها",
        "الجلسات المحفوظة كلها", "الجلسات المحفوظة وملخصاتها كلها",
        "نلخصات الجلسات", "اعرض نلخصات الجلسات",
        "اكتب ملخصات الجلسات المحفوظة كلها",
        "اعرض ملخصات الجلسة المحفوظة",
    )
    if any(token in text for token in list_markers) or (
        any(token in text for token in ("استرجع", "استعد", "استكمل"))
        and any(token in text for token in ("جلسة محفوظة", "الجلسة المحفوظة"))
    ):
        return {"kind": "list", "report_mode": report_mode}
    if any(token in text for token in (
        "لخص ما فعلناه", "ملخص الجلسة", "ملخص جلسة", "استكمل الجلسة",
        "استرجع الجلسة", "استعد الجلسة", "استكمال الجلسة", "أين توقفنا",
        "اين توقفنا", "ما مضمون الجلسة", "تقرير كامل عن الجلسة", "أعطني تقرير كامل", "أعطني تقريرًا كاملًا",
    )):
        return {"kind": "latest", "report_mode": report_mode}
    return {"kind": "none"}


def resolve_saved_session_choice(raw: str, candidates: list[dict]) -> str | None:
    """Resolve a reply to a displayed saved-session ambiguity without guessing."""
    if not isinstance(candidates, list) or not candidates:
        return None

    def normalized(value: object) -> str:
        value = str(value or "").casefold()
        value = (
            value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ى", "ي").replace("ـ", "")
        )
        value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
        value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
        return " ".join(value.split())

    text = normalized(raw)
    if not text:
        return None

    raw_folded = str(raw or "").casefold()
    for item in candidates:
        session_id = str(item.get("session_id") or "").strip()
        if session_id and session_id.casefold() in raw_folded:
            return session_id

    numeric = re.fullmatch(r"(?:الخيار|الاختيار|option)?\s*(\d+)", text)
    if numeric:
        number = int(numeric.group(1))
        if 1 <= number <= len(candidates):
            return str(candidates[number - 1].get("session_id") or "") or None

    ordinals = (
        (1, ("الاولى", "الاول", "الخيار الاول", "الاختيار الاول", "النتيجة الاولى", "المرشح الاول")),
        (2, ("الثانية", "الثاني", "الخيار الثاني", "الاختيار الثاني", "النتيجة الثانية", "المرشح الثاني")),
        (3, ("الثالثة", "الثالث", "الخيار الثالث", "الاختيار الثالث", "النتيجة الثالثة", "المرشح الثالث")),
        (4, ("الرابعة", "الرابع", "الخيار الرابع", "الاختيار الرابع", "النتيجة الرابعة", "المرشح الرابع")),
        (5, ("الخامسة", "الخامس", "الخيار الخامس", "الاختيار الخامس", "النتيجة الخامسة", "المرشح الخامس")),
    )
    for number, phrases in ordinals:
        if number <= len(candidates) and any(phrase in text for phrase in phrases):
            return str(candidates[number - 1].get("session_id") or "") or None

    exact_matches = []
    for item in candidates:
        fields = (item.get("title"), item.get("topic"), item.get("active_goal"))
        if any(
            len(normalized(field)) >= 5
            and (normalized(field) in text or text in normalized(field))
            for field in fields
        ):
            exact_matches.append(item)
    unique_ids = {
        str(item.get("session_id") or "").strip()
        for item in exact_matches
        if str(item.get("session_id") or "").strip()
    }
    if len(unique_ids) == 1:
        return next(iter(unique_ids))

    stop_words = {
        "جلسة", "الجلسة", "جلسه", "الجلسه", "جلسات", "الجلسات",
        "ملخص", "الملخص", "اكتب", "اعرض", "استرجع", "استعد", "اختر",
        "الخيار", "الاختيار", "هذه", "هذا", "التي", "الذي", "عرضتها",
        "انت", "انا", "كنا", "نتحدث", "نتكلم", "عن", "حول", "موضوع",
        "المحفوظة", "المحفوظ", "في", "من", "على", "و", "او", "ثم",
        "مع", "كل", "جميع", "رقم", "اختصر", "اكمل", "تقرير",
    }
    query_tokens = {
        token for token in re.findall(r"[\w]+", text, flags=re.UNICODE)
        if len(token) > 1 and token not in stop_words
    }
    if len(query_tokens) < 2:
        return None

    scored = []
    for item in candidates:
        haystack = normalized(" ".join(
            str(item.get(key) or "")
            for key in ("title", "topic", "active_goal", "summary")
        ))
        candidate_tokens = set(re.findall(r"[\w]+", haystack, flags=re.UNICODE))
        scored.append((len(query_tokens & candidate_tokens), str(item.get("session_id") or "").strip()))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 2 and scored[0][1] and (
        len(scored) == 1 or scored[0][0] > scored[1][0]
    ):
        return scored[0][1]
    return None

def save_session(active_goal: str = None, completed: list = None,
                 next_step: str = None, last_files: list = None,
                 version: str = "unknown", *, dialogue_state: dict = None,
                 context_state: dict = None, project_root: str = None,
                 decisions: list = None, open_questions: list = None,
                 title: str = None, session_type: str = None,
                 status: str = None, project: str = None,
                 summary: str = None):
    now = datetime.now().isoformat()
    data = {
        "schema_version": SESSION_SCHEMA_VERSION,
        "session_id"   : f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:8]}",
        "version"      : version,
        "created_at"   : now,
        "updated_at"   : now,
        "timestamp"    : now,
        "title"        : title or active_goal or "جلسة غير معنونة",
        "session_type" : session_type or ("mixed" if dialogue_state and context_state else "dialogue" if dialogue_state else "work"),
        "status"       : status or ("paused" if next_step else "completed"),
        "project"      : project or project_root or "",
        "summary"      : summary or "",
        "active_goal"  : active_goal or "",
        "completed_work": completed or [],
        "next_step"    : next_step or "",
        "last_files"   : last_files or [],
    }
    if dialogue_state is not None:
        data["dialogue_state"] = dialogue_state
    if context_state is not None:
        data["context_state"] = context_state
    if project_root:
        data["project_root"] = project_root
    if decisions is not None:
        data["decisions"] = list(decisions)
    if open_questions is not None:
        data["open_questions"] = list(open_questions)
    _enrich_session_fields(data)
    # المسار الرئيسي: project_knowledge (Single Writer)
    # الـ fallback: كتابة مباشرة فقط عند فشل الاستيراد (استثناء معروف)
    try:
        from lab_v4_dev.awareness.project_knowledge import save_session as pk_save
        pk_save(data)
    except Exception:
        # FALLBACK — يُستخدم فقط إذا تعذر استيراد project_knowledge
        path = _session_file()
        from lab_v4_dev.memory.intelligence import atomic_write_json
        atomic_write_json(path, data)
    _write_session_detail(data)
    _append_recent_archive(data)
    return data


def save_recoverable_checkpoint(*, active_goal: str = "", next_step: str = "",
                                last_files: list = None, version: str = "unknown",
                                dialogue_state: dict = None, context_state: dict = None,
                                project_root: str = None, decisions: list = None,
                                open_questions: list = None) -> dict:
    """Persist a bounded checkpoint without replacing existing work metadata."""
    existing = load_session()
    data = dict(existing or {})
    next_step_provided = bool(str(next_step or "").strip())
    now = datetime.now().isoformat()
    data.update({
        "schema_version": data.get("schema_version", SESSION_SCHEMA_VERSION),
        "session_id": data.get("session_id") or f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:8]}",
        "updated_at": now,
        "timestamp": now,
        "version": version or data.get("version", "unknown"),
        "active_goal": active_goal or data.get("active_goal", ""),
        "next_step": next_step or data.get("next_step", ""),
        "last_files": list(last_files or data.get("last_files", [])),
    })
    data.setdefault("created_at", data.get("timestamp"))
    data["title"] = active_goal or data.get("title") or "جلسة عمل"
    # This record is the canonical recoverable work checkpoint. Dialogue is
    # persisted independently and cannot change the work session's type.
    data["session_type"] = "work"
    data.pop("dialogue_state", None)
    previous_status = str(data.get("status") or "").casefold()
    last_result = (context_state or data.get("context_state") or {}).get("last_result", {})
    last_result_status = str(last_result.get("status") if isinstance(last_result, dict) else "").casefold()
    if last_result_status in {"failed", "error"}:
        data["status"] = "failed"
    elif next_step_provided:
        data["status"] = "paused"
    elif previous_status in {"completed", "paused", "failed", "active"}:
        data["status"] = previous_status
    else:
        data["status"] = "completed" if not data.get("next_step") else "paused"
    data.setdefault("project", project_root or data.get("project_root", ""))
    data.setdefault("summary", "")
    # Do not mix dialogue history into the canonical work checkpoint.
    data.pop("dialogue_state", None)
    if context_state is not None:
        data["context_state"] = context_state
    if project_root:
        data["project_root"] = project_root
    if decisions is not None:
        data["decisions"] = list(decisions)
    if open_questions is not None:
        data["open_questions"] = list(open_questions)
    _enrich_session_fields(data)
    try:
        from lab_v4_dev.awareness.project_knowledge import save_session as pk_save
        pk_save(data)
    except Exception:
        path = _session_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    _write_session_detail(data)
    _append_recent_archive(data)
    return data

def save_dialogue_checkpoint(*, dialogue_state: dict, version: str = "unknown",
                             project_root: str = None) -> dict:
    """Persist dialogue history without replacing the canonical work checkpoint."""
    if not isinstance(dialogue_state, dict):
        return {}

    # A dialogue snapshot without an explicit identity cannot safely own
    # topic metadata or turns. Live DialogueState snapshots always carry one.
    state = dict(dialogue_state)
    session_id = str(state.get("session_id") or "").strip()
    if not session_id:
        return {}

    # Keep records from this exact dialogue session and exclude work/system
    # state even when legacy callers shared one DialogueMemory instance.
    def is_dialogue_record(item: dict) -> bool:
        if str(item.get("session_id") or "") != session_id:
            return False
        kind = str(item.get("context_kind") or "").casefold()
        domain = str(item.get("conversation_domain") or "").casefold()
        if kind in {"work", "system"} or domain in {"work", "system", "execution"}:
            return False
        # Some educational explanations are handled by the execution owner but
        # still belong to technical dialogue. Keep those; reject actual
        # execution-domain records regardless of their context_kind label.
        return kind != "execution" or domain == "technical"

    history = [
        turn for turn in (state.get("history") or [])
        if isinstance(turn, dict) and is_dialogue_record(turn)
    ]
    exchanges = [
        exchange for exchange in (state.get("exchange_archive") or [])
        if isinstance(exchange, dict) and is_dialogue_record(exchange)
    ]
    state["history"] = history[-8:]
    state["exchange_archive"] = exchanges[-32:]

    index = get_session_index()
    previous = next(
        (item for item in sorted(index, key=_session_updated_key, reverse=True)
         if str(item.get("session_type") or "").casefold() == "dialogue"),
        {},
    )
    current = load_session()
    previous_id = previous.get("session_id")
    # A legacy mixed record can share its ID with the canonical work pointer.
    # Do not mutate that work identity into a dialogue session.
    same_as_work = (
        previous_id
        and isinstance(current, dict)
        and current.get("session_id") == previous_id
        and str(current.get("session_type") or "work").casefold() != "dialogue"
    )
    # An explicitly empty dialogue snapshot represents a reset, not an
    # update to the previous dialogue session. Give it a new ID so the old
    # topic cannot remain the latest recoverable dialogue checkpoint.
    empty_dialogue_reset = (
        not str(state.get("last_topic") or state.get("pending_topic") or "").strip()
        and not history
        and not exchanges
        and not (state.get("context_history") or [])
    )
    # A checkpoint belongs to the dialogue session that produced it.
    # Reusing the latest dialogue record for a different in-memory session
    # makes the archive ID disagree with dialogue_state.session_id and can
    # cause restore to select the wrong transcript.
    data = (
        {}
        if empty_dialogue_reset
        else get_session_by_id(session_id)
    )
    now = datetime.now().isoformat()
    if not isinstance(data, dict) or not data:
        data = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:8]}",
            "created_at": now,
        }
    topic = str(state.get("last_topic") or state.get("pending_topic") or "").strip()
    data.update({
        "schema_version": data.get("schema_version", SESSION_SCHEMA_VERSION),
        "session_id": session_id,
        "updated_at": now,
        "timestamp": now,
        "version": version or data.get("version", "unknown"),
        "title": f"حوار: {topic}" if topic else "جلسة حوار",
        "session_type": "dialogue",
        "status": "completed",
        "active_goal": topic or "حفظ سياق الحوار",
        "next_step": "",
        "last_files": [],
        "project": project_root or data.get("project", ""),
        "dialogue_state": state,
    })
    # A dialogue checkpoint must never retain execution context from a legacy
    # mixed record.
    data.pop("context_state", None)
    data.pop("project_root", None)
    data.pop("decisions", None)
    data.pop("open_questions", None)
    _enrich_session_fields(data)
    _write_session_detail(data)
    _append_recent_archive(data)
    return data


def load_session() -> dict:
    try:
        from lab_v4_dev.awareness.project_knowledge import get_session_state
        return get_session_state()
    except Exception:
        return {}


def recoverable_work_checkpoint(data: dict | None = None) -> dict | None:
    """Return a checkpoint only when it contains verifiable executable work.

    A saved dialogue summary is intentionally not enough to resume work. The
    caller needs a concrete goal and next step plus either a recoverable
    execution intent or a file that still exists under the saved project root.
    """
    checkpoint = data if isinstance(data, dict) else load_session()
    if not isinstance(checkpoint, dict):
        return None
    if str(checkpoint.get("session_type") or "").casefold() == "dialogue":
        return None
    goal = str(checkpoint.get("active_goal") or "").strip()
    next_step = str(checkpoint.get("next_step") or "").strip()
    if not goal or not next_step:
        return None
    generic = {"مشروع", "عمل جاري", "حفظ الجلسة", "استكمال الجلسة", "جلسة جديدة"}
    if goal.casefold() in generic or next_step.casefold() in generic:
        return None

    context = checkpoint.get("context_state") or {}
    if not isinstance(context, dict):
        context = {}
    intent = str(context.get("last_intent") or "").casefold()
    recoverable_intents = {
        "modify_code", "modify_file", "generate_code", "create_file",
        "analyze_code", "delete_file", "run", "run_file", "run_project",
        "run_tests", "test_project", "test_file", "cleanup_code",
        "repair_approve", "refactor_file", "session_save",
    }
    files = list(checkpoint.get("last_files") or [])
    for candidate in (context.get("current_file"), context.get("file"), *files):
        if not candidate:
            continue
        path = os.path.expanduser(str(candidate))
        if not os.path.isabs(path):
            root = checkpoint.get("project_root")
            path = os.path.join(str(root), path) if root else path
        if os.path.isfile(path):
            return {
                "checkpoint": checkpoint,
                "goal": goal,
                "next_step": next_step,
                "file": os.path.abspath(path),
                "intent": intent,
            }
    if intent in recoverable_intents and (context.get("subject") or goal):
        return {
            "checkpoint": checkpoint,
            "goal": goal,
            "next_step": next_step,
            "file": None,
            "intent": intent,
        }
    return None


def _as_clean_list(value) -> list[str]:
    if not isinstance(value, (list, tuple)):
        value = [value] if value else []
    return [str(item).strip() for item in value if str(item).strip()]


def _evidence_labels(value) -> list[str]:
    """Return labels only from structured records with positive evidence.

    Free-form descriptions are deliberately ignored here.  They remain
    available through ``completed_work``/pending fields, but cannot establish
    that an operation actually completed successfully.
    """
    labels = []
    items = value if isinstance(value, (list, tuple)) else ([value] if value else [])
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("result") or "").casefold()
        verified = item.get("verified") is True or item.get("passed") is True or item.get("executed") is True
        positive = status in {"success", "passed", "pass", "verified", "completed", "ok"}
        if not (verified or positive):
            continue
        label = item.get("label") or item.get("step") or item.get("action") or item.get("intent") or item.get("step_id")
        if label:
            labels.append(str(label).strip())
    return list(dict.fromkeys(label for label in labels if label))


def _structured_topics(dialogue: dict) -> list[str]:
    topics = []
    for key in ("exchange_archive", "history", "turns"):
        records = dialogue.get(key, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            for field in ("target", "topic", "entity", "subject"):
                value = str(record.get(field) or "").strip()
                if value and value not in topics:
                    topics.append(value)
    return topics


def analyze_session(data: dict | None = None) -> dict:
    """Derive a grounded semantic report without exposing transcript content."""
    session = data if isinstance(data, dict) else load_session()
    session = session if isinstance(session, dict) else {}
    dialogue = session.get("dialogue_state") or {}
    context = session.get("context_state") or {}
    if not isinstance(dialogue, dict):
        dialogue = {}
    if not isinstance(context, dict):
        context = {}
    result = context.get("last_result") or {}
    if not isinstance(result, dict):
        result = {}

    structured_topics = _structured_topics(dialogue)
    topic = (dialogue.get("last_topic") or context.get("subject")
             or context.get("current_subject") or (structured_topics[-1] if structured_topics else None)
             or session.get("topic") or session.get("active_goal"))
    goal = session.get("active_goal") or context.get("current_subject")
    # Keep descriptive work history, but do not treat it as proof.
    completed = _as_clean_list(session.get("completed_work"))
    confirmed = _evidence_labels(session.get("confirmed_achievements"))
    for field in ("execution_results", "test_results", "verified_results", "results"):
        for label in _evidence_labels(session.get(field)):
            if label not in confirmed:
                confirmed.append(label)
    if result.get("status") == "success" and result.get("executed") is True:
        label = result.get("label") or result.get("action") or result.get("intent") or context.get("last_intent")
        if label and str(label).strip() not in confirmed:
            confirmed.append(str(label).strip())

    last_result_status = str(result.get("status") or "").casefold()
    status = str(session.get("status") or "").casefold()
    if status not in {"completed", "paused", "failed", "active", "running"}:
        status = ""
    if last_result_status in {"failed", "error"}:
        status = "failed"
    elif session.get("next_step") and status == "completed":
        status = "paused"
    elif not status:
        status = "paused" if session.get("next_step") else "completed" if confirmed else "active"

    pending = _as_clean_list(session.get("pending_tasks"))
    if not pending:
        pending = _as_clean_list(session.get("open_questions"))
    next_step = str(session.get("next_step") or (pending[0] if pending else "غير محدد من البيانات المتاحة")).strip()
    if next_step != "غير محدد من البيانات المتاحة" and next_step not in pending:
        pending.insert(0, next_step)
    files = _as_clean_list(session.get("relevant_files"))
    for item in [*_as_clean_list(session.get("last_files")), context.get("current_file")]:
        item = str(item or "").strip()
        if item and item not in files:
            files.append(item)
    decisions = _as_clean_list(session.get("decisions"))
    topics = structured_topics
    for item in [dialogue.get("last_topic"), context.get("subject"), context.get("current_subject"), topic]:
        item = str(item or "").strip()
        if item and item not in topics:
            topics.append(item)
    session_type = str(session.get("session_type") or "").strip()
    if not session_type:
        intent = str(context.get("last_intent") or "").casefold()
        session_type = "educational" if intent in {"cyber_explain", "analyze_code"} and not files else "programming" if files or intent in {"modify_code", "generate_code", "run_tests"} else "planning"
    current_state = {
        "failed": "فشلت آخر عملية مثبتة",
        "paused": "المهمة متوقفة عند الخطوة التالية",
        "completed": "المهمة مكتملة حسب الأدلة المحفوظة",
        "running": "المهمة قيد التنفيذ",
        "active": "المهمة نشطة دون نقطة توقف تنفيذية",
    }.get(status, "غير محدد من البيانات المتاحة")
    return {
        "session_id": session.get("session_id") or "غير محدد من البيانات المتاحة",
        "topic": str(topic or "غير محدد من البيانات المتاحة"),
        "active_goal": str(goal or "غير محدد من البيانات المتاحة"),
        "session_type": session_type,
        "status": status,
        "current_state": current_state,
        "completed_work": completed,
        "unverified_work": [item for item in completed if item not in confirmed],
        "confirmed_achievements": confirmed,
        "last_completed_step": confirmed[-1] if confirmed else "غير محدد من البيانات المتاحة",
        "pending_tasks": pending,
        "next_step": next_step,
        "relevant_files": files,
        "decisions": decisions,
        "open_questions": _as_clean_list(session.get("open_questions")),
        "topics": topics,
        "last_updated": session.get("updated_at") or session.get("timestamp") or "غير محدد من البيانات المتاحة",
    }

def _dialogue_exchanges(data: dict) -> list[dict]:
    """Return only completed exchanges belonging to the selected saved dialogue."""
    dialogue = data.get("dialogue_state") or {}
    if not isinstance(dialogue, dict):
        return []
    session_id = str(dialogue.get("session_id") or "").strip()
    exchanges = dialogue.get("exchange_archive") or []
    if not isinstance(exchanges, list):
        return []
    return [
        item for item in exchanges
        if isinstance(item, dict)
        and not item.get("recall_only")
        and not item.get("state_boundary_only")
        and str(item.get("session_id") or "") == session_id
        and str(item.get("user") or "").strip()
        and str(item.get("assistant") or "").strip()
        and not item.get("response_failed")
    ]


def _is_dialogue_control_text(value: object) -> bool:
    """Identify session-management/meta turns that are not topic content."""
    text = " ".join(str(value or "").split()).strip().casefold()
    text = (
        text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        .replace("ى", "ي").replace("ـ", "")
    )
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = " ".join(text.split())
    if not text:
        return True
    if text in {
        "مرحبا", "اهلا", "اهلا وسهلا", "السلام عليكم", "صباح الخير",
        "مساء الخير", "كيفك ايها الوكيل", "كيف حالك", "كيف الحال",
        "كيف حالك اليوم", "كيف حال الوكيل", "كيف داز نهارك",
        "ميف الحال", "انا بخير", "بخير", "جيد", "نعم", "اجل",
        "حسنا", "تمام",
        # Standalone dialogue-control turns are not subject matter. A request
        # carrying an explicit topic (for example, "اكمل عن الفضاء") remains
        # eligible for semantic extraction.
        "حسنا اكمل", "حسنا نكمل", "اكمل", "اكمل الحديث",
        "لنكمل حوارنا", "هيا نكمل حديثنا", "دعنا نواصل حديثنا",
        "دعنا نتحدث قليلا", "دعنا نتكلم قليلا", "تابع الشرح",
        "واصل الشرح", "ماهي اخر نقطة توقف فيها الحوار",
        "ما هي اخر نقطة توقف فيها الحوار",
    } or re.fullmatch(
        r"(?:كيف|ميف)\s+(?:الحال|حالك|حالكم|حال الوكيل)(?:\s+اليوم)?",
        text,
    ):
        return True
    session_words = ("جلسة", "الجلسة", "جلسات", "الجلسات", "حوار", "الحوار")
    management_words = (
        "ملخص", "ملخصات", "لخص", "تلخيص", "تقرير", "استرجع", "استعد",
        "استكمل", "استكمال", "اعرض", "اكتب", "احفظ", "حفظ", "ماذا كنا نقول",
        "ما كنا نقول", "ماذا كنا نتحدث", "ما كنا نتحدث", "اين توقفنا",
        "اكتب ملخص", "اكتب تقرير", "المضمون",
    )
    if any(word in text for word in management_words) and any(
        word in text for word in session_words
    ):
        return True
    if any(phrase in text for phrase in (
        "ماذا كنا نقول في اخر جلسة", "ماذا كنا نقول في الجلسة السابقة",
        "كنا نتحدث في الجلسة السابقة", "كنا نتحدث في اخر جلسة",
        "ملخص هذه الجلسة", "ملخص الجلسة المحفوظة",
    )):
        return True
    return False


def _is_dialogue_control_exchange(exchange: dict) -> bool:
    """A saved exchange can remain in transcripts but must not pollute summaries."""
    return _is_dialogue_control_text(exchange.get("user"))


def _dialogue_exchange_insights(exchange: dict) -> list[str]:
    """Extract a grounded semantic point from one exchange, never a raw Q/A line."""
    user_text = " ".join(str(exchange.get("user") or "").split()).strip()
    if not user_text or _is_dialogue_control_text(user_text):
        return []

    insights = []
    for field in (
        "semantic_summary", "summary", "gist", "key_points",
        "main_points", "topics_discussed",
    ):
        value = exchange.get(field)
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for candidate in values:
            item = " ".join(str(candidate or "").split()).strip(" \t\r\n-•")
            if item and item not in insights:
                insights.append(item)
    if insights:
        return insights[:4]

    normalized = (
        user_text.casefold()
        .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        .replace("ى", "ي").replace("ـ", "")
    )
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", normalized)
    topic = " ".join(str(exchange.get("target") or "").split()).strip()
    answer = " ".join(str(exchange.get("assistant") or "").split()).strip()
    answer = re.split(r"(?<=[.!?؟])\s+", answer, maxsplit=1)[0].strip()
    answer = answer.strip(" \t\r\n-•")
    generic_answer_markers = (
        "انا بخير", "أنا بخير", "كيف حالك", "كيف الحال",
        "هل في شيء تحب", "هل ترغب في", "كيف يمكنني مساعدتك",
        "لا املك سجل", "لا أملك سجل", "لم افهم", "لم أفهم",
        "انا جاهز", "أنا جاهز", "اخبرني بما تريد",
    )
    if any(marker.casefold() in answer.casefold() for marker in generic_answer_markers):
        answer = ""
    answer = re.sub(
        r"^(?:الفرق(?:\s+الاساسي)?\s+هو|الاختلاف\s+هو|الخلاصة\s*[:：]?|"
        r"الاجابة\s+هي|ببساطة|بشكل\s+عام|باختصار)\s*",
        "",
        answer,
        flags=re.IGNORECASE,
    ).strip(" \t\r\n.,،؛:!?؟")
    answer = answer[:200]

    # Preserve concise social proposal requests as their subject, not as
    # an unclassified generic exchange. The phrase is embedded in a narrative
    # insight rather than rendered as a user/assistant transcript line.
    suggestion_request = re.match(
        r"^(?:ماذا|ما)\s+تقترح\s+(?:انت|أنت)[؟?!.،؛]*$",
        user_text,
        flags=re.IGNORECASE,
    )
    if suggestion_request:
        return [
            f"تناول الحوار طلب اقتراح من الوكيل بصيغة «{user_text}»؛ "
            + (f"وكان الرد: {answer}." if answer else "دون حفظ اقتراح محدد.")
        ]

    # Recover a user-stated concern as a topic even when it is phrased as a
    # personal observation rather than an explicit question or target.
    learning_concern = re.match(
        r"^أشعر\s+أن\s+(.+?)\s+ولا\s+أعرف\s+ماذا\s+أتعلم[.!؟?]*$",
        user_text,
        flags=re.IGNORECASE,
    )
    if learning_concern:
        subject = learning_concern.group(1).strip()
        return [
            f"ناقش الحوار تسارع «{subject}» وما يمكن تعلمه؛ "
            + (f"واقترح الرد {answer}." if answer else "دون توصية محفوظة.")
        ]

    # Explicit general-topic declarations and conversational topic openings
    # carry usable subject evidence even when the parser supplied no target.
    declared_topic = re.match(
        r"^(?:موضوع|فكرة)\s+(?:عام(?:ة)?\s+)?(?:عن|حول)\s+(.+?)[.!؟?،؛]*$",
        user_text,
        flags=re.IGNORECASE,
    )
    if declared_topic:
        subject = declared_topic.group(1).strip(" \t\r\n.,،؛:!?؟")
        return [
            f"ناقش الحوار موضوعًا عامًا عن «{subject}»؛ "
            + (f"وقدم الرد توضيحًا موجزًا بشأن {answer}." if answer else "دون خلاصة جواب محفوظة.")
        ]

    conversational_topic = re.match(
        r"^(?:نتحدث|نتكلم|نتحاور)\s+(?:عن|حول)\s+(.+?)[.!؟?،؛]*$",
        user_text,
        flags=re.IGNORECASE,
    )
    if conversational_topic:
        subject = conversational_topic.group(1).strip(" \t\r\n.,،؛:!?؟")
        return [
            f"كان محور الحوار الذي حدده المستخدم «{user_text}»؛ "
            + (f"وتناول الرد موضوع «{subject}» بإيجاز: {answer}." if answer else f"وكان موضوعه «{subject}».")
        ]

    # A user may state the discussion subject directly rather than ask a
    # question ("ناقشنا موضوعًا اجتماعيًا"). Preserve that semantic subject
    # in the summary instead of reducing the exchange to the assistant reply.
    discussion_subject = re.match(
        r"^(?:ناقشنا|ناقش\s+الحوار|تحدثنا\s+عن|تناولنا|دار\s+حديثنا\s+عن)\s+(.+?)[؟?!.،؛]*$",
        user_text,
        flags=re.IGNORECASE,
    )
    if discussion_subject:
        subject = discussion_subject.group(1).strip(" \t\r\n.,،؛:!?؟")
        if subject:
            if answer:
                return [
                    f"تناول الحوار {subject}؛ ويتضمن السجل ردًا من الوكيل مضمونه: {answer}."
                ]
            return [f"تناول الحوار {subject}؛ وتبادل الطرفان ردًا حواريًا حوله."]

    comparison = re.search(
        r"(?:ما\s+)?(?:الفرق|الفروق|الاختلاف)\s+بين\s+(.+?)(?:[؟?!.،؛]|$)",
        normalized,
    )
    if comparison:
        pair = " ".join(comparison.group(1).split()).strip(" \t\r\n.,،؛:!?؟")
        if pair:
            return [
                f"قارن الحوار بين «{pair[:150]}»"
                + (f"؛ وتركز التوضيح على {answer}." if answer else ".")
            ]

    if any(marker in normalized for marker in ("ما معنى", "معنى", "ما هو", "ما هي", "تعريف", "عرف", "اشرح", "وضح")):
        if not topic:
            match = re.search(
                r"(?:ما معنى|معنى|ما هو|ما هي|تعريف|عرف|اشرح|وضح)\s+(.+?)(?:[؟?!.،؛]|$)",
                user_text,
            )
            topic = (match.group(1).strip() if match else "")
        prefix = f"تناول الحوار مفهوم «{topic}» وشرحه" if topic else "تناول الحوار سؤالًا تعريفيًا أو تفسيريًا"
        return [
            f"{prefix}؛ وتركز التوضيح على {answer}."
            if answer else f"{prefix}، دون خلاصة جواب كافية محفوظة."
        ]

    if any(marker in normalized for marker in ("اقتراح", "اقترح", "ما الحل", "حل مناسب")):
        prefix = f"تناول الحوار اقتراحات أو حلولًا مرتبطة بـ«{topic}»" if topic else "تناول الحوار اقتراحات أو حلولًا"
        return [
            f"{prefix}؛ وأبرز ما ورد في الرد: {answer}."
            if answer else f"{prefix} دون حفظ خلاصة جواب واضحة."
        ]

    if any(marker in normalized for marker in ("خطة", "خطوات", "الخطوة التالية", "الخطوه التاليه")):
        prefix = f"تناول الحوار التخطيط والخطوات المرتبطة بـ«{topic}»" if topic else "تناول الحوار التخطيط أو ترتيب الخطوات"
        return [
            f"{prefix}؛ والخلاصة المحفوظة: {answer}."
            if answer else f"{prefix} دون خطوات مفصلة محفوظة."
        ]

    if any(marker in normalized for marker in ("لماذا", "ما السبب", "اسباب", "أسباب")):
        prefix = f"ناقش الحوار أسبابًا مرتبطة بـ«{topic}»" if topic else "ناقش الحوار سؤالًا عن الأسباب"
        return [
            f"{prefix}؛ والسبب المذكور في الرد: {answer}."
            if answer else f"{prefix} دون سبب محدد محفوظ."
        ]

    # Do not classify every sentence beginning with "كيف" as a procedure.
    # Greetings such as "كيف الحال؟" were filtered above; only explicit
    # process/method wording qualifies for a how-to summary.
    procedural_how = any(marker in normalized for marker in (
        "كيف يتم", "كيف تعمل", "كيف يعمل", "كيف يمكن", "كيف استخدم",
        "كيف نستخدم", "كيف يحدث", "كيف يحدث", "كيفية", "ما طريقه",
        "ما طريقة", "كيفيه",
    ))
    if procedural_how:
        prefix = f"ناقش الحوار آلية «{topic}» أو طريقة التعامل معها" if topic else "ناقش الحوار طريقة أو آلية محددة"
        return [
            f"{prefix}؛ وأشار الرد إلى {answer}."
            if answer else f"{prefix}، لكن لا توجد خطوات كافية محفوظة."
        ]

    if any(marker in normalized for marker in ("ما رايك", "رايك", "وجهة نظرك", "وجهة النظر")):
        prefix = f"تناول الحوار وجهات نظر حول «{topic}»" if topic else "تناول الحوار تبادل وجهات نظر"
        return [
            f"{prefix}؛ والرأي المسجل: {answer}."
            if answer else f"{prefix} دون رأي محدد محفوظ."
        ]

    if not topic:
        topic_match = re.search(
            r"(?:ماذا تعرف عن|ما الذي تعرفه عن|حدثني عن|تحدث عن|ما حالة|حالة)\s+(.+?)(?:[؟?!.،؛]|$)",
            user_text,
        )
        if topic_match:
            topic = topic_match.group(1).strip()
        elif normalized.startswith(("ماذا تستطيع فعله", "ما الذي تستطيع فعله", "ما قدراتك")):
            topic = "قدرات الوكيل"

    if topic and answer:
        return [f"ناقش الحوار «{topic}»؛ وقدم الرد توضيحًا موجزًا بشأن {answer}."]
    if topic:
        return [f"تناول الحوار موضوع «{topic}»؛ ولا تتوفر خلاصة جواب إضافية محفوظة لهذا التبادل."]
    if answer:
        return [f"تضمن الحوار توضيحًا لموضوع ورد في السؤال؛ وخلاصة الرد: {answer}."]
    return ["يتضمن السجل تبادلًا حواريًا، لكن لا توجد بيانات دلالية كافية لتحديد مضمونه دون تخمين."]

def _dialogue_assistant_insight(exchange: dict) -> str:
    """Extract a concise grounded insight from an assistant turn without quoting the turn."""
    if _is_dialogue_control_exchange(exchange):
        return ""
    text = " ".join(str(exchange.get("assistant") or "").split()).strip()
    if not text:
        return ""
    normalized = (
        text.casefold()
        .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        .replace("ى", "ي").replace("ـ", "")
    )
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", normalized)
    prefixes = (
        ("ناقشنا ", "تناول الحوار "),
        ("ناقشنا: ", "تناول الحوار "),
        ("تناولنا ", "تناول الحوار "),
        ("تحدثنا عن ", "تناول الحوار "),
        ("توقفنا عند ", "نقطة التوقف في الحوار: "),
        ("انتهينا الى ", "انتهى الحوار إلى "),
        ("خلصنا الى ", "خلص الحوار إلى "),
        ("الفرق يرتبط بـ", "وضح الحوار ارتباط الفرق بـ"),
        ("الفرق يرتبط ب", "وضح الحوار ارتباط الفرق بـ"),
        ("الفرق هو ", "يوضح الرد أن "),
        ("الفرق يكمن في ", "وضح الحوار أن الفرق يكمن في "),
    )
    for prefix, replacement in prefixes:
        if normalized.startswith(prefix):
            remainder = text[len(prefix):].strip(" .،؛:!?؟")
            if remainder:
                return (replacement + remainder).rstrip(" .،؛:!?؟") + "."
    # Only retain a compact semantic fragment when the response has recognizable
    # content terms. Do not copy generic acknowledgements or the full response.
    content_markers = (
        "فوائد", "مخاطر", "تقليل", "حماية", "خصوصية", "موافقة",
        "اسباب", "خطوات", "نتيجة", "استنتاج", "توصية",
    )
    if any(marker in normalized for marker in content_markers):
        fragment = text.strip(" .،؛:!?؟")
        if len(fragment) > 180:
            fragment = fragment[:177].rstrip() + "…"
        return "أبرز مضمون محفوظ في رد الوكيل: " + fragment + "."
    return ""


def _dialogue_explicit_conclusions(exchanges: list[dict]) -> list[str]:
    """Collect only conclusions/decisions explicitly stored as structured fields."""
    items = []
    for exchange in exchanges:
        for field in ("decision", "decisions", "conclusion", "outcome", "takeaway", "key_takeaway"):
            value = exchange.get(field)
            values = value if isinstance(value, (list, tuple, set)) else [value]
            for candidate in values:
                item = " ".join(str(candidate or "").split()).strip(" \t\r\n-•")
                if item and item not in items:
                    items.append(item)
    return items




def summarize_dialogue_exchanges(
    exchanges: list[dict] | None,
    *,
    topic: str = "",
    limit: int = 6,
) -> dict:
    """Build a concise narrative summary from the meaning of bounded exchanges."""
    records = [
        item for item in (exchanges or [])
        if isinstance(item, dict)
        and str(item.get("user") or "").strip()
        and str(item.get("assistant") or "").strip()
        and not item.get("recall_only")
        and not item.get("state_boundary_only")
        and not item.get("response_failed")
    ]
    meaningful = [
        item for item in records
        if not _is_dialogue_control_exchange(item)
    ]

    selected_topic = " ".join(str(topic or "").split()).strip()
    if not selected_topic or _is_dialogue_control_text(selected_topic):
        selected_topic = next(
            (
                " ".join(str(item.get("target") or "").split()).strip()
                for item in reversed(meaningful)
                if str(item.get("target") or "").strip()
                and not _is_dialogue_control_text(item.get("target"))
            ),
            "",
        )

    insights = []
    for exchange in meaningful:
        for insight in (
            *_dialogue_exchange_insights(exchange),
            _dialogue_assistant_insight(exchange),
        ):
            insight = " ".join(str(insight or "").split()).strip()
            if insight and insight not in insights:
                insights.append(insight)
    insights = insights[:max(1, int(limit))]

    if not selected_topic and meaningful:
        selected_topic = next(
            (
                " ".join(str(item.get("target") or "").split()).strip()
                for item in meaningful
                if str(item.get("target") or "").strip()
            ),
            "",
        )
    if not selected_topic and insights:
        selected_topic = insights[0][:100].rstrip(" .،؛:")
    if not selected_topic and records:
        selected_topic = "حوار افتتاحي عن التحية والتعارف"

    last = meaningful[-1] if meaningful else {}
    last_target = " ".join(str(last.get("target") or "").split()).strip()
    last_insights = _dialogue_exchange_insights(last) if last else []
    if not meaningful:
        stop_point = "لم يتجاوز السجل تبادل التحية أو الحديث الاجتماعي القصير؛ لم يُسجّل موضوع نقاش فعلي."
    elif last_target and not _is_dialogue_control_text(last_target):
        stop_point = f"توقف الحوار عند مناقشة «{last_target}»؛ ولا توجد متابعة محفوظة بعد آخر تبادل مكتمل."
    elif last_insights:
        stop_point = f"آخر مضمون موثق في السجل: {last_insights[0]}"
    elif insights:
        stop_point = f"آخر نقطة يمكن إثباتها من السجل: {insights[-1]}"
    else:
        stop_point = "توجد تبادلات محفوظة، لكن لا تكفي بياناتها لتحديد نقطة توقف موضوعية دون تخمين."

    return {
        "topic": selected_topic,
        "insights": insights,
        "stop_point": stop_point,
        "exchange_count": len(records),
        "meaningful_exchange_count": len(meaningful),
        "has_substantive_content": bool(meaningful and insights),
    }

def _build_dialogue_session_summary(data: dict, report_mode: str) -> str:
    """Summarize the selected dialogue and its stop point without mixing work state."""
    report = analyze_session(data)
    exchanges = _dialogue_exchanges(data)
    dialogue = data.get("dialogue_state") or {}
    # Keep all exchanges for literal transcript mode, but exclude greetings and
    # session-management commands from semantic topic extraction and summaries.
    summary_exchanges = [
        item for item in exchanges if not _is_dialogue_control_exchange(item)
    ]
    stored_topic = str(
        dialogue.get("last_topic")
        or next((item.get("target") for item in reversed(summary_exchanges) if item.get("target")), "")
        or report.get("topic")
    ).strip()
    generic_topics = {
        "حفظ سياق الحوار", "جلسة حوار", "حوار محفوظ", "غير محدد من سجل الحوار",
        "حوار بلا موضوع محدد", "جلسة بلا عنوان",
    }
    content_topic = next(
        (
            " ".join(str(item.get("target") or item.get("user") or "").split())[:100]
            for item in summary_exchanges
            if " ".join(str(item.get("target") or item.get("user") or "").split()).strip()
        ),
        "",
    )
    stored_topic_is_control = _is_dialogue_control_text(stored_topic)
    topic = (
        stored_topic
        if stored_topic and stored_topic not in generic_topics and not stored_topic_is_control
        else content_topic
    )
    topic = topic or "حوار افتتاحي أو إداري بلا موضوع معرف في السجل"
    last = (summary_exchanges or exchanges)[-1] if (summary_exchanges or exchanges) else {}
    if last:
        stop_point = (
            "توقف الحوار بعد آخر تبادل مكتمل محفوظ؛ "
            + (f"كان موضوع التبادل «{last.get('target')}»." if last.get("target")
               else f"لا يحمل آخر تبادل موضوعًا فرعيًا محددًا؛ الموضوع العام المسجل هو «{topic}».")
            + " يوجد رد محفوظ من الوكيل، ولم تُنشأ متابعة جديدة أثناء الاستعادة."
        )
        next_step = f"استكمال الحوار من آخر تبادل محفوظ حول «{topic}»."
    else:
        stop_point = "لا توجد تبادلات مكتملة محفوظة يمكن تحديد نقطة التوقف منها."
        next_step = "حدّد الموضوع أو اختر جلسة أخرى إذا كان هذا السجل غير مكتمل."

    if report_mode == "transcript":
        lines = [
            "=== نص الحوار المحفوظ حرفيًا ===",
            f"معرّف الجلسة: {report['session_id']}",
            f"الموضوع: {topic}",
        ]
        if not exchanges:
            lines.append("لا يحتوي سجل الجلسة على تبادلات مكتملة قابلة للعرض.")
        for index, exchange in enumerate(exchanges, 1):
            lines.extend([
                "",
                f"[{index}] المستخدم:",
                str(exchange.get("user") or ""),
                f"[{index}] الوكيل:",
                str(exchange.get("assistant") or ""),
            ])
        return "\n".join(lines)

    if report_mode == "compact":
        return "\n".join([
            "=== ملخص الحوار المحفوظ ===",
            f"المعرّف: {report['session_id']}",
            f"الموضوع: {topic}",
            f"عدد التبادلات المكتملة: {len(exchanges)}",
        ])
    if report_mode == "progress":
        progress_summary = summarize_dialogue_exchanges(
            summary_exchanges,
            topic=topic,
            limit=12,
        )
        progress_stop_point = progress_summary["stop_point"]
        progress_next_step = (
            f"استكمال النقاش من آخر مضمون موثق حول «{progress_summary['topic']}»."
            if progress_summary["meaningful_exchange_count"]
            else "اختيار موضوع واضح للبدء؛ السجل الحالي لا يثبت وجود نقاش موضوعي سابق."
        )
        progress_insights = progress_summary["insights"]
        progress_lines = [
            "=== ملخص الحوار ونقطة التوقف ===",
            f"الموضوع: {progress_summary['topic'] or topic}",
            f"التبادلات المكتملة المحفوظة: {len(exchanges)}",
            "",
            "ما ناقشناه فعليًا:",
        ]
        progress_lines.extend(
            [f"- {insight}" for insight in progress_insights]
            if progress_insights
            else ["- لا يتضمن السجل مضمونًا موضوعيًا كافيًا لتلخيصه."]
        )
        progress_lines.extend([
            "",
            f"نقطة التوقف: {progress_stop_point}",
            f"الخطوة التالية: {progress_next_step}",
            "لم يتم تنفيذ أي خطوة جديدة أثناء الاستعادة.",
        ])
        return "\n".join(progress_lines)

    topics = []
    for exchange in summary_exchanges:
        value = " ".join(str(exchange.get("target") or "").split()).strip()
        if value and not _is_dialogue_control_text(value) and value not in topics:
            topics.append(value)

    # Summarize the meaningful bounded archive semantically. Control turns stay
    # available in transcript mode but cannot become the report's subject.
    semantic_summary = summarize_dialogue_exchanges(
        summary_exchanges,
        topic=topic,
        limit=12,
    )
    content_lines = semantic_summary["insights"]
    explicit_conclusions = _dialogue_explicit_conclusions(summary_exchanges)

    lines = [
        "=== ملخص الحوار المحفوظ ===",
        f"معرّف الجلسة: {report['session_id']}",
        f"آخر تحديث: {report['last_updated']}",
        f"الموضوع الحالي داخل هذا الحوار: {topic}",
        f"عدد التبادلات المكتملة المحفوظة: {len(exchanges)}",
        "",
        "ما نوقش فعليًا في الحوار:",
    ]
    lines.extend([f"- {item}" for item in content_lines] if content_lines else [
        "- لا توجد تبادلات مكتملة ذات مضمون قابل للتلخيص في البيانات المحفوظة."
    ])
    lines.extend(["", "الموضوعات المثبتة في سجل الحوار:"])
    lines.extend([f"- {item}" for item in topics] if topics else [
        "- لا توجد موضوعات فرعية محددة في البيانات المحفوظة."
    ])
    lines.extend(["", "الخلاصات والقرارات المسجلة صراحة:"])
    lines.extend([f"- {item}" for item in explicit_conclusions] if explicit_conclusions else [
        "- لا توجد خلاصات أو قرارات منفصلة محفوظة في الحقول المنظمة."
    ])
    lines.extend([
        "",
        "نقطة التوقف:",
        semantic_summary["stop_point"],
        "",
        "الخطوة التالية المقترحة:",
        next_step,
        "",
        "حدود الاستعادة: هذا ملخص للسجل المحدد فقط؛ لم تُدمج معه الجلسة الحية أو جلسة العمل. لم يُنشأ أي رد جديد.",
    ])
    return "\n".join(lines)


def build_session_restore_summary(data: dict | None = None, *, report_mode: str = "standard") -> str:
    """Render a report from the selected session type; never mix dialogue with work state."""
    session = data if isinstance(data, dict) else load_session()
    session = session if isinstance(session, dict) else {}
    session_type = str(session.get("session_type") or "").casefold()
    dialogue_state = session.get("dialogue_state")
    if session_type == "dialogue" or (
        not session_type
        and isinstance(dialogue_state, dict)
        and bool(str(dialogue_state.get("session_id") or "").strip())
        and not session.get("context_state")
    ):
        return _build_dialogue_session_summary(session, report_mode)

    report = analyze_session(session)
    def bullets(items, empty="غير محدد من البيانات المتاحة"):
        return [f"- {item}" for item in (items or [empty])]
    if report_mode == "compact":
        return "\n".join([
            "=== بيانات الجلسة ===",
            f"المعرّف: {report['session_id']}",
            f"الموضوع: {report['topic']}",
            f"الحالة: {report['status']}",
        ])
    if report_mode == "progress":
        return "\n".join([
            "=== حالة التقدم ===",
            f"الموضوع: {report['topic']}",
            f"الحالة الحالية: {report['current_state']}",
            f"آخر إنجاز مؤكد: {report['last_completed_step']}",
            f"نقطة التوقف: {report['next_step']}",
            "الأعمال المتبقية:", *bullets(report['pending_tasks']),
        ])
    lines = [
        "=== التقرير الدلالي للجلسة ===",
        f"معرّف الجلسة: {report['session_id']}",
        f"آخر تحديث: {report['last_updated']}",
        f"نوع الجلسة: {report['session_type']}",
        "",
        "1) الموضوع والهدف",
        f"- الموضوع: {report['topic']}",
        f"- الهدف: {report['active_goal']}",
        "",
        "2) ما نوقش فعليًا",
        *bullets(report['topics']),
        "",
        "3) ما نُفّذ والإنجازات المؤكدة",
        *bullets(report['confirmed_achievements']),
        "",
        "4) أوصاف أعمال غير متحققة",
        *bullets(report['unverified_work']),
        "",
        "5) الحالة الحالية ونقطة التوقف",
        f"- الحالة: {report['status']}",
        f"- وصف الحالة: {report['current_state']}",
        f"- آخر خطوة مؤكدة: {report['last_completed_step']}",
        "",
        "6) الأعمال المتبقية والخطوة التالية",
        *bullets(report['pending_tasks']),
        f"- الخطوة التالية: {report['next_step']}",
        "",
        "7) الملفات والقرارات والقيود المهمة",
        "الملفات:", *bullets(report['relevant_files']),
        "القرارات:", *bullets(report['decisions']),
        "الأسئلة المفتوحة:", *bullets(report['open_questions']),
        "",
        "8) نتيجة الاستعادة",
        "تم تحميل سياق الجلسة المحددة؛ لم يتم تنفيذ الخطوة التالية تلقائيًا.",
    ]
    return "\n".join(lines)


def build_session_brief_summary(data: dict | None = None) -> dict:
    """Build a concise list summary from saved dialogue/work evidence."""
    session = data if isinstance(data, dict) else {}
    report = analyze_session(session)
    session_type = str(session.get("session_type") or report.get("session_type") or "work").casefold()
    dialogue = session.get("dialogue_state") or {}
    if not isinstance(dialogue, dict):
        dialogue = {}

    def clean(value: object, limit: int = 150) -> str:
        value = " ".join(str(value or "").split()).strip()
        return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"

    generic_topics = {
        "", "حفظ سياق الحوار", "حفظ الجلسة", "جلسة حوار", "حوار محفوظ",
        "غير محدد من سجل الحوار", "جلسة بلا عنوان", "عمل جاري",
        "غير محدد من البيانات المتاحة", "غير محدد",
    }

    def useful_topic(value: object) -> bool:
        candidate = clean(value, 100).casefold()
        if candidate in generic_topics:
            return False
        return not any(
            candidate.startswith(generic + " —") or candidate.startswith(generic + " -")
            for generic in generic_topics if generic
        )

    is_dialogue = session_type == "dialogue" or (
        not str(session.get("session_type") or "").strip()
        and isinstance(session.get("dialogue_state"), dict)
        and bool(str(dialogue.get("session_id") or "").strip())
        and not session.get("context_state")
    )

    if is_dialogue:
        exchanges = _dialogue_exchanges(session)
        meaningful_exchanges = [
            item for item in exchanges
            if not _is_dialogue_control_exchange(item)
        ]
        topic_candidates = (
            dialogue.get("last_topic"),
            next((item.get("target") for item in reversed(meaningful_exchanges) if item.get("target")), ""),
            next((item.get("user") for item in meaningful_exchanges if item.get("user")), ""),
            report.get("topic"), session.get("title"), session.get("active_goal"),
        )
        topic = next(
            (
                clean(value, 100)
                for value in topic_candidates
                if useful_topic(value) and not _is_dialogue_control_text(value)
            ),
            "",
        )
        control_phrases = {
            "حفظ سياق الحوار", "حفظ الجلسة", "نفس السياق", "اكمل",
            "اكمل من حيث توقفنا", "اختصر اكثر", "اختصر", "اكتب ملخص هذه الجلسة",
            "اكتب ملخص لكل جلسة", "اكتب تقرير ملخص لكل جلسة",
            "اعرض جميع الجلسات", "اعرض جميع الجلسات المحفوظة",
            "كم عدد الجلسات المحفوظة",
        }
        meaningful_users = []
        greeting_seen = False
        for exchange in exchanges:
            user = clean(exchange.get("user"), 180)
            if not user:
                continue
            normalized_user = user.casefold().replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            normalized_user = re.sub(r"[ًٌٍَُِّْـ]", "", normalized_user)
            normalized_user = " ".join(normalized_user.strip(" .,،؛:!?؟").split())
            if normalized_user in {
                "مرحبا", "اهلا", "اهلا وسهلا", "السلام عليكم",
                "صباح الخير", "مساء الخير",
            }:
                greeting_seen = True
            if _is_dialogue_control_exchange(exchange):
                continue
            if normalized_user in control_phrases:
                continue
            if (
                re.search(r"(?:ملخص|لخص|تلخيص|تقرير).*(?:كل|جميع|الجلسات|الجلسة المحفوظة)", normalized_user)
                or re.search(r"(?:استرجع|استعد|اعرض).*(?:الجلسة رقم|الجلسات المحفوظة)", normalized_user)
            ):
                continue
            if user not in meaningful_users:
                meaningful_users.append(user)

        if not topic and meaningful_users:
            topic = clean(meaningful_users[0], 100)
        topic = topic or "حوار بلا موضوع محدد"
        # Summaries describe the meaning of saved exchanges; verbatim messages
        # remain available only through the explicit transcript report mode.
        semantic_summary = summarize_dialogue_exchanges(
            meaningful_exchanges,
            topic=topic,
            limit=4,
        )
        insights = semantic_summary["insights"]
        if insights:
            summary = "الخلاصة الدلالية للحوار: " + "؛ ".join(
                clean(value, 105) for value in insights[:2]
            ) + "."
        elif meaningful_users:
            summary = (
                f"تناول الحوار موضوع «{topic}»، لكن لا توجد بيانات محفوظة كافية "
                "لاستخلاص تفاصيل أدق دون تخمين."
            )
        elif greeting_seen:
            summary = "حوار افتتاحي للتحية والتعارف؛ لا تظهر في السجل تبادلات موضوعية أخرى مكتملة."
        else:
            summary = "لا يحتوي السجل على تبادلات مكتملة ذات مضمون يمكن تلخيصه بثقة."
        next_step = clean(
            session.get("next_step") or (report.get("next_step") if report.get("next_step") != "غير محدد من البيانات المتاحة" else ""),
            120,
        )
        return {
            "session_id": str(session.get("session_id") or report.get("session_id") or ""),
            "session_type": "dialogue",
            "topic": topic,
            "summary": clean(summary, 270),
            "status": report.get("status", session.get("status", "غير محددة")),
            "next_step": next_step,
        }

    topic_candidates = (
        report.get("topic"), session.get("title"), session.get("active_goal"),
        report.get("active_goal"),
    )
    topic = next(
        (clean(value, 100) for value in topic_candidates if useful_topic(value)),
        "",
    )
    topics = list(report.get("topics") or [])
    completed = list(session.get("completed_work") or [])
    achievements = list(report.get("confirmed_achievements") or [])
    pending = list(report.get("pending_tasks") or [])
    evidence = []
    for value in [*achievements, *completed, *topics]:
        value = clean(value, 100)
        if value and useful_topic(value) and value != topic and value not in evidence:
            evidence.append(value)
    if not topic and evidence:
        topic = evidence.pop(0)
    topic = topic or "جلسة عمل بلا عنوان موثوق"
    parts = [f"الموضوع/الهدف: {topic}."]
    if evidence:
        parts.append(f"المحفوظ من العمل: {evidence[0]}.")
    next_step = clean(session.get("next_step") or (pending[0] if pending else ""), 100)
    if next_step and useful_topic(next_step) and next_step != topic:
        parts.append(f"الخطوة التالية: {next_step}.")
    elif not evidence:
        parts.append("لا توجد إنجازات أو تفاصيل إضافية مؤكدة في البيانات المحفوظة.")
    return {
        "session_id": str(session.get("session_id") or report.get("session_id") or ""),
        "session_type": session_type or "work",
        "topic": topic,
        "summary": clean(" ".join(parts), 270),
        "status": report.get("status", session.get("status", "غير محددة")),
    }

def _enrich_session_fields(data: dict) -> dict:
    """Persist semantic fields so later reports do not depend on live context."""
    # These fields are derived outputs.  Remove their previous values first so
    # a checkpoint cannot keep a stale topic, state, or generic summary.
    for key in (
        "topic", "current_state", "last_completed_step", "pending_tasks",
        "relevant_files", "last_updated", "summary",
    ):
        data.pop(key, None)
    report = analyze_session(data)
    data.update({
        "topic": report["topic"],
        "current_state": report["current_state"],
        "last_completed_step": report["last_completed_step"],
        "pending_tasks": report["pending_tasks"],
        "relevant_files": report["relevant_files"],
        "confirmed_achievements": report["confirmed_achievements"],
        "last_updated": report["last_updated"],
    })
    data["summary"] = build_session_restore_summary(data)
    return data

def clear_session():
    path = _session_file()
    if os.path.exists(path):
        os.remove(path)
