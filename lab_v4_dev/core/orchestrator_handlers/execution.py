"""Script inventory, dry-run and execution-history query handlers."""

import os

from lab_v4_dev.core.project_context import CYBERLAB_ROOT

WORKSPACE_DIR = os.path.join(CYBERLAB_ROOT, "workspace")

def handle_list_scripts(orchestrator, intent, *, target=None, raw=None):

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
