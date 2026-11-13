"""Repair queue and rejection handlers."""


def handle_repair_reject(orchestrator, intent, *, target=None, raw=None):
    orchestrator.context.last_result = None
    return {"status":"success","intent":intent,
            "text":"تم رفض الإصلاح — لم يتم تعديل أي شيء"}


def handle_pending_fixes(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.repair.diff_approval import list_pending
    pending = list_pending()
    if not pending:
        return {"status":"success","intent":intent,
                "text":"لا توجد إصلاحات معلقة ✅"}
    lines = ["=== الإصلاحات المعلقة ==="]
    for p in pending:
        lines.append(f"⏳ {p['fix']}")
    return {"status":"success","intent":intent,"text":"\n".join(lines)}


__all__ = ["handle_repair_reject", "handle_pending_fixes"]


def handle_repair_analyze(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    from lab_v4_dev.core.repair.error_reader import get_latest_error
    from lab_v4_dev.core.repair.error_analyzer import analyze
    from lab_v4_dev.core.repair.fix_generator import generate_fix
    from lab_v4_dev.core.repair.diff_approval import show_fix_proposal, save_pending_fix

    error = get_latest_error()
    if not error or not error.get("message"):
        return {"status": "success", "intent": intent, "text": "لا توجد أخطاء مسجلة ✅"}
    analysis = analyze(error, authorized_ask=authorized_ask)
    if not analysis.get("fixable", False):
        return {
            "status": "success", "intent": intent,
            "text": f"الخطأ: {error.get('message', '')}\nيحتاج مراجعة يدوية",
        }
    fix = generate_fix(error, analysis, authorized_ask=authorized_ask)
    proposal = show_fix_proposal(fix, error)
    path = save_pending_fix(error.get("file", ""), fix, error, analysis)
    orchestrator.context.last_result = {"pending_path": path, "fix": fix}
    return {"status": "success", "intent": intent, "text": proposal}


def handle_repair_approve(orchestrator, intent, *, target=None, raw=None):
    import os
    from lab_v4_dev.core.repair.diff_approval import apply_fix, list_pending

    last = orchestrator.context.last_result or {}
    pending_path = last.get("pending_path", "")
    if not pending_path:
        pending = list_pending()
        if pending:
            pending_path = os.path.join("workspace/pending_fixes", pending[0]["file"])
    if not pending_path:
        return {"status": "failed", "intent": intent, "text": "لا يوجد إصلاح معلق"}
    result = apply_fix(pending_path, approved=True)
    return {
        "status": result["status"], "intent": intent,
        "text": f"{'✅' if result['status'] == 'success' else '❌'} {result['message']}",
    }


__all__ = ["handle_repair_reject", "handle_pending_fixes", "handle_repair_analyze", "handle_repair_approve"]
