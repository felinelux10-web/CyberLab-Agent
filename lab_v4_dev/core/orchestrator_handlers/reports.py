"""Report and work-tracking handlers migrated from Orchestrator._route."""

import os
from datetime import datetime

from lab_v4_dev.intent.intents import Intent


def handle_session_report(orchestrator, intent, *, target=None, raw=None):
    summary = orchestrator.services.session.summary()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return {
        "status": "success",
        "intent": intent,
        "time": now,
        "session": summary,
    }


def handle_project_reports(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    if authorized_ask is None:
        return {
            "status": "unavailable",
            "intent": intent,
            "source": "provider_policy",
            "text": "بوابة المزود المصرح بها غير متاحة لهذا المسار.",
        }

    from lab_v4_dev.awareness.project_memory import load_memory
    from lab_v4_dev.awareness.knowledge_retriever import resolve_project_scope
    from lab_v4_dev.config.provider_config import get_active_provider
    from lab_v4_dev.llm.prompt_builder import build_project_context

    memory = load_memory()
    total = memory.get("total_files", 0)
    system = build_project_context(
        question=raw,
        intent=intent,
        project_scope=resolve_project_scope(raw, intent=intent),
    )
    result = authorized_ask(raw, system=system, max_tokens=400)
    return {
        "status": result["status"],
        "intent": intent,
        "source": result.get("provider_used", get_active_provider()),
        "text": result.get("text", ""),
    }


def handle_context_report(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.project_context import CYBERLAB_ROOT
    from lab_v4_dev.core.project_metadata import ProjectMetadata

    metadata = ProjectMetadata()
    tasks = orchestrator.services.memory.recent_tasks(10)
    releases_dir = os.path.join(CYBERLAB_ROOT, "releases")
    releases = sorted([
        name for name in os.listdir(releases_dir)
        if os.path.isdir(os.path.join(releases_dir, name))
    ]) if os.path.exists(releases_dir) else []
    current_phase = metadata.get_current_phase()
    return {
        "status": "success",
        "intent": intent,
        "version": metadata.get_version(),
        "focus": metadata.get_project_name(),
        "phases": [current_phase.get("name", "?")] if current_phase else [],
        "releases": releases,
        "tasks": [
            {"status": task["status"], "intent": task["intent"][:60]}
            for task in tasks
        ],
    }


def handle_history(orchestrator, intent, *, target=None, raw=None):
    tasks = orchestrator.services.memory.recent_tasks(10)
    return {
        "status": "success",
        "intent": intent,
        "tasks": [
            {"status": task["status"], "intent": task["intent"][:50]}
            for task in tasks
        ],
    }


def handle_work_tracking(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.data.work_tracker import get_status, get_next_task, get_remaining

    status = get_status()
    if intent == Intent.NEXT_TASK:
        return {
            "status": "success",
            "intent": intent,
            "text": f"المهمة التالية: {get_next_task()}",
        }
    if intent == Intent.REMAINING_TASKS:
        remaining = get_remaining()
        text = "المتبقي:\n" + "\n".join(f"  - {task}" for task in remaining)
        return {"status": "success", "intent": intent, "text": text}

    lines = [
        f"الإصدار: {status['version']}",
        f"التركيز: {status['current_focus']}",
        f"مكتمل  : {', '.join(status['completed']) or 'لا شيء'}",
        f"نشط    : {', '.join(status['active']) or 'لا شيء'}",
        f"مخطط   : {', '.join(status['planned']) or 'لا شيء'}",
    ]
    if status["blocked"]:
        lines.append(f"محظور  : {', '.join(status['blocked'])}")
    return {"status": "success", "intent": intent, "text": chr(10).join(lines)}


def handle_work_context(orchestrator, intent, *, target=None, raw=None):
    lines = ["=== سجل العمل الحالي ==="]
    tasks = orchestrator.services.memory.recent_tasks(8)
    if tasks:
        lines.append("\n📋 العمليات المسجلة فعليًا:")
        for task in tasks:
            detail = str(task.get("plan") or task.get("intent") or "").strip()
            lines.append(f"  [{task['status']}] {detail[:120]}")
    else:
        lines.append("\nلا توجد عمليات عمل مسجلة في هذه الجلسة.")

    from lab_v4_dev.core.repair.diff_approval import list_pending
    pending = list_pending()
    if pending:
        lines.append(f"\n⏳ إصلاحات معلقة ({len(pending)}):")
        for item in pending:
            lines.append(f"  - {item['fix']}")

    return {"status": "success", "intent": intent, "text": chr(10).join(lines)}


def handle_show_last_result(orchestrator, intent, *, target=None, raw=None):
    data = orchestrator.context.last_result
    if not data:
        return {
            "status": "success",
            "intent": intent,
            "text": "لا يوجد نتيجة سابقة",
        }
    output = data.get("text") or data.get("output") or str(data)[:300]
    return {"status": "success", "intent": intent, "text": output}


def handle_show_changes(orchestrator, intent, *, target=None, raw=None):
    tasks = orchestrator.services.memory.recent_tasks(10)
    lines = ["آخر التعديلات:"]
    for t in tasks:
        icon = "✅" if t["status"] == "success" else "❌"
        lines.append(f"  {icon} {t['intent'][:40]}")
    return {
        "status": "success",
        "intent": intent,
        "text"  : chr(10).join(lines),
        "tasks" : [{"intent": t["intent"][:40],
                    "status": t["status"]} for t in tasks],
    }


__all__ = [
    "handle_session_report",
    "handle_project_reports",
    "handle_context_report",
    "handle_history",
    "handle_work_tracking",
    "handle_work_context",
    "handle_show_last_result",
]
