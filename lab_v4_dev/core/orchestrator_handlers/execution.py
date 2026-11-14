"""Script inventory, dry-run and execution-history query handlers."""

import os

def handle_list_scripts(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.project_context import CYBERLAB_ROOT
    WORKSPACE_DIR = os.path.join(CYBERLAB_ROOT, "workspace")

    scripts = []
    for folder in ["scripts","modified","analysis"]:
        path = os.path.join(WORKSPACE_DIR, folder)
        if os.path.exists(path):
            for f in os.listdir(path):
                scripts.append(f"{folder}/{f}")
    if not scripts:
        return {"status":"success","intent":intent,
                "text":"لا توجد سكريبتات محفوظة بعد"}
    text = "السكريبتات المحفوظة:\n" + "\n".join(f"  📄 {s}" for s in scripts)
    return {"status":"success","intent":intent,"text":text}


def handle_error_report(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.sandbox_executor import list_error_reports
    reports = list_error_reports()
    if not reports:
        return {"status":"success","intent":intent,"text":"لا توجد أخطاء مسجلة ✅"}
    lines = ["=== سجل الأخطاء ==="]
    for r in reports[-5:]:
        approved = "✅" if r["approved"] else "⏳"
        lines.append(f"{approved} {r['file']}")
        lines.append(f"   {r['error'][:60]}")
    return {"status":"success","intent":intent,"text":"\n".join(lines)}


def handle_dry_run(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.project_context import CYBERLAB_ROOT
    WORKSPACE_DIR = os.path.join(CYBERLAB_ROOT, "workspace")
    from lab_v4_dev.core.sandbox_executor import dry_run

    scripts_dir = os.path.join(WORKSPACE_DIR, "scripts")
    scripts = sorted(
        [f for f in os.listdir(scripts_dir) if f.endswith(".py")],
        key=lambda x: os.path.getmtime(os.path.join(scripts_dir, x)),
        reverse=True
    ) if os.path.exists(scripts_dir) else []
    if not scripts:
        return {"status":"failed","intent":intent,"text":"لا توجد سكريبتات"}
    last = os.path.join(WORKSPACE_DIR, "scripts", scripts[0])
    r    = dry_run(last)
    return {"status":"success","intent":intent,
            "text":f"فحص: {last}\n{r['message'] if r['status']=='ok' else r['error']}"}


def handle_run_history(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.execution_history import get_history
    history = get_history(10)
    if not history:
        return {"status":"success","intent":intent,"text":"لا يوجد تاريخ تشغيل بعد"}
    lines = ["=== سجل التشغيل ==="]
    for r in history[:5]:
        icon = "✅" if r["status"]=="success" else "❌"
        lines.append(f"{icon} {r['script'].split('/')[-1]} — {r['duration']}s")
    return {"status":"success","intent":intent,"text":"\n".join(lines)}


__all__ = ["handle_list_scripts", "handle_error_report", "handle_dry_run", "handle_run_history"]


def handle_run_script(orchestrator, intent, *, target=None, raw=None):
    import os
    import shlex
    import time
    from lab_v4_dev.core.contracts import Context
    from lab_v4_dev.core.project_context import CYBERLAB_ROOT
    from lab_v4_dev.core.security_guard import check_path

    workspace_dir = os.path.realpath(os.path.join(CYBERLAB_ROOT, "workspace"))
    scripts_dir = os.path.join(workspace_dir, "scripts")
    scripts = sorted(
        [name for name in os.listdir(scripts_dir) if name.endswith(".py")],
        key=lambda name: os.path.getmtime(os.path.join(scripts_dir, name)),
        reverse=True,
    ) if os.path.isdir(scripts_dir) else []

    raw_text = str(raw or "")
    selected_path = None

    if target:
        raw_target = os.path.expanduser(str(target))
        candidate = (
            os.path.realpath(raw_target)
            if os.path.isabs(raw_target)
            else os.path.realpath(os.path.join(workspace_dir, raw_target))
        )
        if os.path.isfile(candidate):
            selected_path = candidate

    if selected_path is None:
        for name in scripts:
            if name in raw_text:
                selected_path = os.path.realpath(os.path.join(scripts_dir, name))
                break

    if selected_path is None:
        last_result = getattr(orchestrator.context, "last_result", None) or {}
        saved = last_result.get("saved_to", "") if isinstance(last_result, dict) else ""
        if saved and os.path.isfile(saved):
            selected_path = os.path.realpath(saved)

    if selected_path is None:
        available = "، ".join(scripts[:8]) if scripts else "لا توجد سكريبتات محفوظة"
        return {
            "status": "needs_clarification",
            "intent": intent,
            "executed": False,
            "text": "حدّد اسم السكريبت المطلوب تشغيله؛ لن أختار أحدث ملف تلقائيًا. المتاح: " + available,
        }

    try:
        if os.path.commonpath([workspace_dir, selected_path]) != workspace_dir:
            return {
                "status": "blocked",
                "intent": intent,
                "executed": False,
                "text": "مسار السكريبت خارج مساحة العمل المسموح بها.",
            }
    except ValueError:
        return {
            "status": "blocked",
            "intent": intent,
            "executed": False,
            "text": "مسار السكريبت غير صالح.",
        }

    if not selected_path.endswith(".py"):
        return {
            "status": "blocked",
            "intent": intent,
            "executed": False,
            "text": "يسمح هذا المسار بتشغيل ملفات Python فقط.",
        }

    path_check = check_path(selected_path)
    if not path_check.get("safe", False):
        return {
            "status": "blocked",
            "intent": intent,
            "executed": False,
            "text": path_check.get("reason", "المسار مرفوض من حارس الأمان."),
        }

    submit_prepared = getattr(orchestrator.services, "submit_prepared_execution", None)
    route_decision = getattr(orchestrator.request, "route_decision", None)
    if not callable(submit_prepared):
        return {
            "status": "denied",
            "intent": intent,
            "executed": False,
            "source": "prepared_execution_capability_missing",
            "text": "قناة التنفيذ المجهزة غير متاحة لهذا المعالج.",
        }

    request_context = Context.from_store(orchestrator.context)
    execution = {
        "action": "run_command",
        "parameters": {"command": "python3 " + shlex.quote(selected_path)},
    }
    started_at = time.monotonic()
    result = submit_prepared(
        intent,
        target=selected_path,
        context=request_context,
        execution=execution,
        route_decision=route_decision,
    )
    duration = round(time.monotonic() - started_at, 2)

    if not isinstance(result, dict):
        return {
            "status": "failed",
            "intent": intent,
            "executed": False,
            "text": "لم تُرجع حلقة التنفيذ نتيجة صالحة.",
        }

    execution_results = result.get("results") or []
    successful = (
        result.get("status") == "executed"
        and bool(execution_results)
        and all(item.get("status") == "success" for item in execution_results)
    )
    first = execution_results[0] if execution_results else {}
    output = first.get("stdout") or ""
    attempted = result.get("status") == "executed" and bool(execution_results)
    history_warning = None

    if attempted:
        try:
            from lab_v4_dev.core.execution_history import save_run
            history_status = "success" if successful else "error"
            history_error = "" if successful else (
                first.get("error") or first.get("stderr")
                or result.get("reason") or "execution failed"
            )
            save_run(
                selected_path,
                history_status,
                duration,
                first.get("exit_code", 0 if successful else -1),
                history_error,
            )
        except Exception as exc:
            history_warning = str(exc)

    if successful:
        response = {
            "status": "success",
            "intent": intent,
            "executed": True,
            "source": "event_loop.prepared",
            "file": selected_path,
            "text": f"✅ {selected_path}\n{output or 'اكتمل التشغيل دون مخرجات.'}",
            "execution": result,
        }
        if history_warning:
            response["history_warning"] = history_warning
        return response

    reason = result.get("reason") or first.get("error") or first.get("stderr") or result.get("status")
    return {
        "status": result.get("status") if result.get("status") in {"blocked", "denied"} else "error",
        "intent": intent,
        "executed": False,
        "source": "event_loop.prepared",
        "file": selected_path,
        "text": f"❌ تعذر تشغيل {selected_path}: {reason}",
        "execution": result,
    }


__all__ = ["handle_list_scripts", "handle_error_report", "handle_dry_run", "handle_run_history", "handle_run_script"]
