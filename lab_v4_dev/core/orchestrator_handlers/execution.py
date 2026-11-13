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
    from lab_v4_dev.core.project_context import CYBERLAB_ROOT
    from lab_v4_dev.core.sandbox_executor import run_code

    workspace_dir = os.path.join(CYBERLAB_ROOT, "workspace")
    scripts_dir = os.path.join(workspace_dir, "scripts")
    scripts = sorted(
        [name for name in os.listdir(scripts_dir) if name.endswith(".py")],
        key=lambda name: os.path.getmtime(os.path.join(scripts_dir, name)),
        reverse=True,
    ) if os.path.exists(scripts_dir) else []
    if not scripts:
        return {"status": "failed", "intent": intent, "text": "لا توجد سكريبتات محفوظة"}

    target_script = None
    raw_text = str(raw or "")
    for name in scripts:
        if name in raw_text:
            target_script = os.path.join(scripts_dir, name)
            break
    if not target_script:
        last_result = getattr(orchestrator.context, "last_result", None) or {}
        saved = last_result.get("saved_to", "")
        if saved and os.path.exists(saved):
            target_script = saved
    if not target_script:
        target_script = os.path.join(scripts_dir, scripts[0])

    result = run_code(target_script, timeout=10)
    if result.get("status") == "success":
        meta = f"⏱ {result.get('duration', '?')}s | exit: {result.get('exit_code', 0)}"
        return {
            "status": "success", "intent": intent,
            "text": f"✅ {target_script}\n{meta}\n\n{result.get('output', 'لا يوجد output')}",
        }
    meta = f"⏱ {result.get('duration', '?')}s | exit: {result.get('exit_code', '?')}"
    return {
        "status": "error",
        "intent": intent,
        "text": f"❌ {target_script}\n{meta}\n{result.get('error', '')}\nتقرير: {result.get('report', '')}",
    }


__all__ = ["handle_list_scripts", "handle_error_report", "handle_dry_run", "handle_run_history", "handle_run_script"]
