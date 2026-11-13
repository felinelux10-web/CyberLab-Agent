"""Read-only system inspection handlers migrated from Orchestrator._route."""

import os
import shutil

from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.awareness.project_memory import load_memory


def handle_space(orchestrator, intent, *, target=None, raw=None):
    total, used, free = shutil.disk_usage(os.path.expanduser("~"))
    return {
        "status": "success", "intent": intent,
        "total": f"{total // (1024 ** 3)}GB",
        "used": f"{used // (1024 ** 2)}MB",
        "free": f"{free // (1024 ** 2)}MB",
    }


def handle_status(orchestrator, intent, *, target=None, raw=None):
    state = orchestrator.agent.state
    summary = orchestrator.agent.session.summary()
    lines = [
        f"الوضع     : {state.mode}",
        f"المهام    : {summary['tasks_done']}",
        f"الأخطاء   : {summary['error_count']}",
        f"الإخفاقات : {state.consecutive_failures}",
    ]
    return {
        "status": "success", "intent": intent,
        "text": chr(10).join(lines),
        "mode": state.mode,
        "failures": state.consecutive_failures,
        "tasks": summary["tasks_done"],
        "errors": summary["error_count"],
    }


def handle_health(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.monitor.health_check import check_health

    health = check_health(orchestrator.agent.state)
    return {"status": "success", "intent": intent, "health": health}


def handle_memory_status(orchestrator, intent, *, target=None, raw=None):
    memory = load_memory()
    return {
        "status": "success", "intent": intent,
        "total_files": memory.get("total_files", 0),
        "last_updated": memory.get("last_updated", "unknown"),
    }


def handle_system_status(orchestrator, intent, *, target=None, raw=None):
    # Keep this as an in-process, read-only diagnostic. Do not launch the
    # legacy project_status.py script through a shell.
    from lab_v4_dev.monitor.health_check import check_health

    health = check_health(orchestrator.agent.state)
    lines = [
        f"حالة النظام: {'سليم' if health.get('healthy') else 'يحتاج إلى مراجعة'}",
        f"وضع التشغيل: {health.get('state_mode', 'غير معروف')}",
        f"الذاكرة: {'سليمة' if health.get('ram_ok') else 'تجاوزت الحد'}"
        + (f" ({health.get('ram_mb')} MB)" if health.get("ram_mb") is not None else ""),
        f"قاعدة البيانات: {'سليمة' if health.get('db_ok') else 'مشكلة في الفحص'}",
        f"السجل: {'سليم' if health.get('log_ok') else 'تجاوز الحد'}",
        f"الشجرة القديمة stable: {health.get('stable_status', 'غير محددة')}",
    ]
    return {
        "status": "success", "intent": intent,
        "text": chr(10).join(lines),
        "health": health,
    }


__all__ = [
    "handle_space", "handle_status", "handle_health",
    "handle_memory_status", "handle_system_status",
    "handle_audit_log", "handle_security_log", "handle_diagnostics",
]


def handle_audit_log(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.audit import get_events

    events = get_events(limit=20)
    if not events:
        from lab_v4_dev.core.safe_io import get_audit_log
        legacy_events = get_audit_log(10)
        if not legacy_events:
            return {"status": "success", "intent": intent, "text": "لا توجد عمليات موثقة في سجل الأدلة حتى الآن."}
        lines = ["=== سجل عمليات الكتابة السابق (آخر 10) ==="]
        for item in legacy_events:
            status_icon = "✅" if item.get("status") == "success" else "❌"
            lines.append(f"{status_icon} {item.get('timestamp', '')[:16]} | {item.get('path', '')}")
        return {"status": "success", "intent": intent, "text": chr(10).join(lines)}

    lines = ["=== سجل الأدلة والعمليات (آخر 20) ==="]
    for item in events:
        context = item.get("context") if isinstance(item.get("context"), dict) else {}
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        event_name = str(item.get("event") or "event")
        status_icon = "❌" if event_name.endswith((".failed", ".failure")) else "✅"
        timestamp = str(item.get("timestamp") or "")[:16]
        source = str(item.get("source") or "unknown")
        lines.append(f"{status_icon} {timestamp} | {event_name} [{source}]")
        file_path = context.get("file_path") or context.get("file") or details.get("file")
        project_root = context.get("project_root") or context.get("root")
        if file_path:
            lines.append(f"    الملف: {file_path}")
        if project_root:
            lines.append(f"    المشروع: {project_root}")
        for key in ("project_name", "project_type", "total_files", "files_modified", "reason"):
            value = details.get(key)
            if value not in (None, "", [], {}):
                lines.append(f"    {key}: {value}")
    return {"status": "success", "intent": intent, "text": chr(10).join(lines)}


def handle_security_log(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.security_guard import get_security_log

    events = get_security_log(20)
    if not events:
        return {"status": "success", "intent": intent, "text": "✅ لا توجد تهديدات مسجلة"}
    lines = ["=== سجل الأمان ==="]
    for event in events:
        timestamp = event.get("timestamp", "")[:16]
        lines.append(f"⚠️ {timestamp} | {event.get('type', '')} | {event.get('value', '')[:50]}")
        lines.append(f"    تطابق: {event.get('matched', '')}")
    return {"status": "success", "intent": intent, "text": chr(10).join(lines)}


def handle_diagnostics(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    from lab_v4_dev.monitor.self_diagnostics import run_diagnostics, format_quick, format_full

    quick = intent == Intent.SELF_DIAGNOSE
    result = run_diagnostics(quick=quick, authorized_ask=authorized_ask)
    text = format_quick(result) if quick else format_full(result, orchestrator.context)
    return {
        "status": "success",
        "intent": intent,
        "text": text,
        "health": result["health"],
    }
