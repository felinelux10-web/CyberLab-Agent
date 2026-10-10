# CyberLab Agent v4.8
# memory/session_state.py

import json
import os
from datetime import datetime

def _session_file() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("session_state.json")


MAX_RECENT_SESSIONS = 5


def _archive_file() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("session_archive.json")


def _append_recent_archive(data: dict) -> None:
    """Keep compact summaries only; never archive the bounded transcript."""
    path = _archive_file()
    try:
        with open(path, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = []
    if not isinstance(archive, list):
        archive = []
    summary = {
        key: data.get(key)
        for key in (
            "session_id", "timestamp", "active_goal", "completed_work",
            "next_step", "last_files", "decisions", "open_questions", "project_root",
        )
        if key in data
    }
    if archive and archive[-1].get("session_id") == summary.get("session_id"):
        archive[-1] = summary
    else:
        archive.append(summary)
    archive = archive[-MAX_RECENT_SESSIONS:]
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

def save_session(active_goal: str = None, completed: list = None,
                 next_step: str = None, last_files: list = None,
                 version: str = "unknown", *, dialogue_state: dict = None,
                 context_state: dict = None, project_root: str = None,
                 decisions: list = None, open_questions: list = None):
    data = {
        "session_id"   : datetime.now().strftime("%Y%m%d_%H%M%S"),
        "version"      : version,
        "timestamp"    : datetime.now().isoformat(),
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
    data.update({
        "session_id": data.get("session_id") or datetime.now().strftime("%Y%m%d_%H%M%S"),
        "timestamp": datetime.now().isoformat(),
        "version": version or data.get("version", "unknown"),
        "active_goal": active_goal or data.get("active_goal", ""),
        "next_step": next_step or data.get("next_step", ""),
        "last_files": list(last_files or data.get("last_files", [])),
    })
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
    try:
        from lab_v4_dev.awareness.project_knowledge import save_session as pk_save
        pk_save(data)
    except Exception:
        path = _session_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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


def build_session_restore_summary(data: dict | None = None) -> str:
    """Render the complete bounded session context for an explicit restore.

    This is deliberately a local renderer: restoring a session must explain
    the saved state without calling an LLM, executing a task, or flattening
    dialogue turns into an ambiguous paragraph.
    """
    session = data if isinstance(data, dict) else load_session()
    if not isinstance(session, dict) or not session:
        return "لا توجد جلسة سابقة محفوظة."

    def value(key: str, default: str = "غير مسجل") -> str:
        raw = session.get(key)
        if raw is None or raw == "":
            return default
        return str(raw)

    def bullet_list(items, empty: str = "لا يوجد") -> list[str]:
        if not isinstance(items, (list, tuple)):
            items = [items] if items else []
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        return [f"- {item}" for item in cleaned] or [f"- {empty}"]

    dialogue = session.get("dialogue_state") or {}
    if not isinstance(dialogue, dict):
        dialogue = {}
    exchanges = [
        item for item in (dialogue.get("exchange_archive") or [])
        if isinstance(item, dict)
        and (str(item.get("user") or "").strip() or str(item.get("assistant") or "").strip())
    ]
    # Older checkpoints may have turns but no exchange archive. Preserve the
    # available transcript rather than claiming that the dialogue is empty.
    if not exchanges:
        turns = [item for item in (dialogue.get("history") or []) if isinstance(item, dict)]
        pending_user = None
        for turn in turns:
            role = str(turn.get("role") or "").casefold()
            content = str(turn.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                pending_user = content
            elif role == "assistant":
                exchanges.append({"user": pending_user or "", "assistant": content})
                pending_user = None
        if pending_user:
            exchanges.append({"user": pending_user, "assistant": ""})

    lines = [
        "=== ملخص استرجاع الجلسة ===",
        f"معرّف الجلسة: {value('session_id')}",
        f"وقت الحفظ: {value('timestamp')}",
        "",
        "1) ماذا كنا نفعل؟",
        f"- الهدف الحالي: {value('active_goal')}",
        f"- الموضوع الحواري النشط: {str(dialogue.get('last_topic') or 'غير مسجل')}",
        "",
        "2) ماذا فعلنا؟",
        *bullet_list(session.get("completed_work"), "لا توجد إنجازات مسجلة"),
        "",
        "3) أين توقفنا؟",
        f"- الخطوة التالية: {value('next_step')}",
        f"- النية الأخيرة: {str((session.get('context_state') or {}).get('last_intent') or 'غير مسجلة')}",
        "",
        "4) الملفات والسياق التنفيذي:",
        *bullet_list(session.get("last_files"), "لا توجد ملفات مسجلة"),
        "",
        "5) القرارات المتخذة:",
        *bullet_list(session.get("decisions"), "لا توجد قرارات مسجلة"),
        "",
        "6) الأسئلة أو الأمور المفتوحة:",
        *bullet_list(session.get("open_questions"), "لا توجد أمور مفتوحة مسجلة"),
        "",
        "7) مضمون الحوار المحفوظ كاملًا:",
    ]
    if exchanges:
        for index, exchange in enumerate(exchanges, 1):
            user = str(exchange.get("user") or "").strip()
            assistant = str(exchange.get("assistant") or "").strip()
            lines.append(f"[{index}] المستخدم: {user or 'غير مسجل'}")
            lines.append(f"    الوكيل: {assistant or 'لا توجد إجابة محفوظة'}")
    else:
        lines.append("- لا يوجد مضمون حواري محفوظ في هذه الجلسة.")
    lines.extend([
        "",
        "8) حالة الاستعادة:",
        "- تمت استعادة المعلومات فقط؛ لم يتم تنفيذ الخطوة التالية تلقائيًا.",
    ])
    return "\n".join(lines)

def clear_session():
    path = _session_file()
    if os.path.exists(path):
        os.remove(path)
