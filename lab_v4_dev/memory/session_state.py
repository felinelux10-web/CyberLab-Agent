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
            "session_type", "status", "project", "summary", "active_goal",
            "completed_work", "next_step", "last_files", "decisions",
            "open_questions", "project_root",
        )
        if key in data
    }
    if archive and archive[-1].get("session_id") == summary.get("session_id"):
        archive[-1] = summary
    else:
        archive.append(summary)
    # The archive is the durable searchable index. The UI helper below still
    # returns only a small recent window for mobile/Termux memory limits.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def get_recent_sessions() -> list:
    try:
        with open(_archive_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data[-MAX_RECENT_SESSIONS:] if isinstance(data, list) else []
    except Exception:
        return []


def get_session_index() -> list:
    """Load the compact durable index without loading dialogue transcripts."""
    try:
        with open(_archive_file(), encoding="utf-8") as f:
            data = json.load(f)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
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
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


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
        "title", "project", "session_type", "status", "summary",
        "active_goal", "next_step", "completed_work", "decisions", "open_questions",
    )
    return " ".join(str(item.get(field, "")) for field in fields).casefold()


def search_sessions(query: str = "", *, status: str | None = None,
                    project: str | None = None, limit: int = 10) -> list:
    """Search compact session metadata; details are loaded only after selection."""
    needle = str(query or "").strip().casefold()
    stop_words = {"جلسة", "الجلسة", "جلسه", "التي", "كنا", "في", "على", "إلى", "الى", "أريد", "اريد", "العودة", "ارجع", "استعد", "استرجع", "مشروع"}
    tokens = [token for token in needle.split() if token not in stop_words and len(token) > 0]
    def contains_token(field: str, token: str) -> bool:
        if token.isdigit():
            return bool(re.search(rf"(?<!\d){re.escape(token)}(?!\d)", field))
        return token in field
    results = []
    for item in reversed(get_session_index()):
        if status and str(item.get("status", "")).casefold() != str(status).casefold():
            continue
        if project and str(project).casefold() not in _session_text(item):
            continue
        haystack = _session_text(item)
        if needle and needle not in haystack and not (tokens and all(contains_token(haystack, token) for token in tokens)):
            continue
        score = 0
        if needle:
            for key in ("title", "project", "active_goal", "summary", "next_step"):
                field = str(item.get(key, "")).casefold()
                matched_tokens = sum(contains_token(field, token) for token in tokens)
                if needle in field or matched_tokens:
                    score += (3 if key in {"title", "project", "active_goal"} else 1) * max(1, matched_tokens)
        results.append({**item, "match_score": score})
        if len(results) >= max(1, int(limit)):
            break
    return sorted(results, key=lambda item: (item.get("match_score", 0), item.get("updated_at", item.get("timestamp", ""))), reverse=True)


def get_session_by_id(session_id: str) -> dict:
    """Return the full selected session, never a different current session."""
    wanted = str(session_id or "").strip()
    if not wanted:
        return {}
    current = load_session()
    if isinstance(current, dict) and current.get("session_id") == wanted:
        return current
    detail = _load_session_detail(wanted)
    if detail:
        return detail
    for item in get_session_index():
        if item.get("session_id") == wanted:
            return item
    return {}


def session_selector(raw: str) -> dict:
    """Classify explicit session selection/report language without an LLM."""
    raw_text = str(raw or "").strip()
    text = raw_text.casefold()
    report_mode = "standard"
    if any(token in text for token in ("فقط", "المعرف والحالة", "المعرّف والموضوع والحالة")):
        report_mode = "compact"
    elif any(token in text for token in ("أين توقفنا", "اين توقفنا", "الخطوة التالية", "ما الذي أُنجز", "ما الذي انجز")):
        report_mode = "progress"
    elif any(token in text for token in ("تقرير كامل", "تقريرًا كاملًا", "تقريرا كاملا")):
        report_mode = "full"
    id_match = re.search(r"(?:معرّف|معرف|id)\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9_.-]{5,})", raw_text, flags=re.IGNORECASE)
    if id_match and any(token in text for token in ("جلسة", "استعد", "استرجع", "ابحث")):
        return {"kind": "id", "session_id": id_match.group(1), "report_mode": report_mode}
    if any(token in text for token in ("الجلسات المعلقة", "جلسات معلقة", "المهام المعلقة")):
        return {"kind": "status", "status": "paused", "report_mode": report_mode}
    if "قارن" in text and any(token in text for token in ("الجلسات", "جلستين", "جلسة")):
        return {"kind": "compare", "report_mode": "full"}
    if any(token in text for token in ("آخر جلسة", "اخر جلسة", "الجلسة الأخيرة", "الجلسه الاخيره")):
        return {"kind": "latest", "report_mode": report_mode}
    search_marker = re.search(r"(?:عن|حول)\s+(.*?)(?:،|,|\s+واعرض|\s+ثم|\s+فقط|$)", raw_text, flags=re.IGNORECASE)
    if any(token in text for token in ("ابحث في الجلسات", "ابحث عن جلسة", "جلسة مشروع", "جلسه مشروع", "جلسة إصلاح", "جلسة اختبار", "جلسه اختبار", "جلسة التي", "جلسه التي")):
        query = search_marker.group(1).strip() if search_marker else raw_text
        query = re.sub(r"^(?:جلسة|الجلسة|جلسه|الجلسه)\s+", "", query, flags=re.IGNORECASE).strip()
        return {"kind": "search", "query": query, "report_mode": report_mode}
    if any(token in text for token in (
        "لخص ما فعلناه", "ملخص الجلسة", "ملخص جلسة", "استكمل الجلسة",
        "استرجع الجلسة", "استعد الجلسة", "استكمال الجلسة", "أين توقفنا",
        "اين توقفنا", "ما مضمون الجلسة", "تقرير كامل عن الجلسة", "أعطني تقرير كامل", "أعطني تقريرًا كاملًا",
    )):
        return {"kind": "latest", "report_mode": report_mode}
    return {"kind": "none"}

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
    if not data["summary"]:
        completed_text = "، ".join(str(item) for item in data["completed_work"][:3]) or "لا توجد إنجازات مسجلة"
        data["summary"] = f"الهدف: {data['active_goal'] or 'غير مسجل'}؛ أُنجز: {completed_text}؛ التوقف: {data['next_step'] or 'غير محدد'}"
    _enrich_session_fields(data)
    # المسار الرئيسي: project_knowledge (Single Writer)
    # الـ fallback: كتابة مباشرة فقط عند فشل الاستيراد (استثناء معروف)
    try:
        from lab_v4_dev.awareness.project_knowledge import save_session as pk_save
        pk_save(data)
    except Exception:
        # FALLBACK — يُستخدم فقط إذا تعذر استيراد project_knowledge
        path = _session_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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
    data.setdefault("title", data.get("active_goal") or "جلسة غير معنونة")
    data.setdefault("session_type", "mixed" if dialogue_state and context_state else "work")
    data.setdefault("status", "paused" if data.get("next_step") else "completed")
    data.setdefault("project", project_root or data.get("project_root", ""))
    data.setdefault("summary", "")
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
    if not data["summary"]:
        completed_text = "، ".join(str(item) for item in data.get("completed_work", [])[:3]) or "لا توجد إنجازات مسجلة"
        data["summary"] = f"الهدف: {data.get('active_goal') or 'غير مسجل'}؛ أُنجز: {completed_text}؛ التوقف: {data.get('next_step') or 'غير محدد'}"
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

def load_session() -> dict:
    try:
        from lab_v4_dev.awareness.project_knowledge import get_session_state
        return get_session_state()
    except:
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

    topic = (
        session.get("topic") or dialogue.get("last_topic") or context.get("subject")
        or context.get("current_subject") or session.get("active_goal")
    )
    goal = session.get("active_goal") or context.get("current_subject")
    completed = _as_clean_list(session.get("completed_work"))
    confirmed = _as_clean_list(session.get("confirmed_achievements"))
    if not confirmed:
        confirmed = list(completed)
    # Only an explicitly successful execution is promoted to a confirmed result.
    if result.get("status") == "success" and result.get("executed") is True:
        intent = str(result.get("intent") or context.get("last_intent") or "").strip()
        if intent:
            marker = f"اكتمل تنفيذ العملية: {intent}"
            if marker not in confirmed:
                confirmed.append(marker)
    last_result_status = str(result.get("status") or "").casefold()
    status = str(session.get("status") or "").strip()
    if not status:
        status = "failed" if last_result_status in {"failed", "error"} else "paused" if session.get("next_step") else "completed" if confirmed else "active"
    last_completed = session.get("last_completed_step")
    if not last_completed:
        last_completed = confirmed[-1] if confirmed else "غير محدد من البيانات المتاحة"
    pending = _as_clean_list(session.get("pending_tasks"))
    if not pending:
        pending = _as_clean_list(session.get("open_questions"))
    if not pending and session.get("next_step"):
        pending = [str(session.get("next_step")).strip()]
    next_step = session.get("next_step") or (pending[0] if pending else "غير محدد من البيانات المتاحة")
    files = _as_clean_list(session.get("relevant_files"))
    for item in [*_as_clean_list(session.get("last_files")), context.get("current_file")]:
        item = str(item or "").strip()
        if item and item not in files:
            files.append(item)
    decisions = _as_clean_list(session.get("decisions"))
    topics = []
    context_history = dialogue.get("context_history", [])
    if not isinstance(context_history, list):
        context_history = []
    for item in [dialogue.get("last_topic"), topic, *context_history]:
        if isinstance(item, dict):
            item = item.get("entity")
        item = str(item or "").strip()
        if item and item not in topics:
            topics.append(item)
    session_type = str(session.get("session_type") or "").strip()
    if not session_type:
        intent = str(context.get("last_intent") or "").casefold()
        session_type = "educational" if intent in {"cyber_explain", "analyze_code"} and not files else "programming" if files or intent in {"modify_code", "generate_code", "run_tests"} else "planning"
    current_state = session.get("current_state") or (
        "فشلت آخر عملية مثبتة" if status == "failed" else "المهمة متوقفة عند الخطوة التالية" if status == "paused" else "المهمة مكتملة حسب البيانات المحفوظة" if status == "completed" else "العمل جارٍ"
    )
    return {
        "session_id": session.get("session_id") or "غير محدد من البيانات المتاحة",
        "topic": str(topic or "غير محدد من البيانات المتاحة"),
        "active_goal": str(goal or "غير محدد من البيانات المتاحة"),
        "session_type": session_type,
        "status": status,
        "current_state": str(current_state),
        "completed_work": completed,
        "confirmed_achievements": confirmed,
        "last_completed_step": str(last_completed),
        "pending_tasks": pending,
        "next_step": str(next_step),
        "relevant_files": files,
        "decisions": decisions,
        "open_questions": _as_clean_list(session.get("open_questions")),
        "topics": topics,
        "last_updated": session.get("updated_at") or session.get("timestamp") or "غير محدد من البيانات المتاحة",
    }


def build_session_restore_summary(data: dict | None = None, *, report_mode: str = "standard") -> str:
    """Render a grounded semantic report; never render the saved transcript."""
    report = analyze_session(data)
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
        "4) الحالة الحالية ونقطة التوقف",
        f"- الحالة: {report['status']}",
        f"- وصف الحالة: {report['current_state']}",
        f"- آخر خطوة مؤكدة: {report['last_completed_step']}",
        "",
        "5) الأعمال المتبقية والخطوة التالية",
        *bullets(report['pending_tasks']),
        f"- الخطوة التالية: {report['next_step']}",
        "",
        "6) الملفات والقرارات والقيود المهمة",
        "الملفات:", *bullets(report['relevant_files']),
        "القرارات:", *bullets(report['decisions']),
        "الأسئلة المفتوحة:", *bullets(report['open_questions']),
        "",
        "7) نتيجة الاستعادة",
        "تم تحميل السياق الدلالي فقط؛ لم يتم عرض سجل الحوار الحرفي؛ لم يتم تنفيذ الخطوة التالية تلقائيًا.",
    ]
    return "\n".join(lines)


def _enrich_session_fields(data: dict) -> dict:
    """Persist semantic fields so later reports do not depend on live context."""
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
    if not data.get("summary"):
        data["summary"] = (
            f"الموضوع: {report['topic']}؛ الحالة: {report['status']}؛ "
            f"آخر إنجاز مؤكد: {report['last_completed_step']}؛ "
            f"الخطوة التالية: {report['next_step']}"
        )
    return data

def clear_session():
    path = _session_file()
    if os.path.exists(path):
        os.remove(path)
