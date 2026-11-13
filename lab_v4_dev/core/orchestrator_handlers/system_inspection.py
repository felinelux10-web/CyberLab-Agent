"""Read-only system inspection handlers migrated from Orchestrator._route."""

import os
import shutil

from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.awareness.project_memory import load_memory


def handle_space(orchestrator, intent):
    total, used, free = shutil.disk_usage(os.path.expanduser("~"))
    return {
        "status": "success", "intent": intent,
        "total": f"{total // (1024 ** 3)}GB",
        "used": f"{used // (1024 ** 2)}MB",
        "free": f"{free // (1024 ** 2)}MB",
    }


def handle_status(orchestrator, intent):
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


def handle_health(orchestrator, intent):
    from lab_v4_dev.monitor.health_check import check_health

    health = check_health(orchestrator.agent.state)
    return {"status": "success", "intent": intent, "health": health}


def handle_memory_status(orchestrator, intent):
    memory = load_memory()
    return {
        "status": "success", "intent": intent,
        "total_files": memory.get("total_files", 0),
        "last_updated": memory.get("last_updated", "unknown"),
    }


def handle_system_status(orchestrator, intent):
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
        "text": "\\n".join(lines),
        "health": health,
    }


__all__ = [
    "handle_space", "handle_status", "handle_health",
    "handle_memory_status", "handle_system_status",
]
