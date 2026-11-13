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
