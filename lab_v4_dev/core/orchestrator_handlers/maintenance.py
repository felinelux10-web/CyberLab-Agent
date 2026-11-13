"""Non-destructive maintenance intent handlers."""


def handle_clean(orchestrator, intent, *, target=None, raw=None):
    return {
        "status": "needs_clarification",
        "intent": intent,
        "text": "ما الذي تريد تنظيفه؟ حدّد الهدف قبل المتابعة.",
    }


__all__ = ["handle_clean"]


def handle_clean_device(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.cleaner import run_full_clean

    result = run_full_clean()
    lines = ["=== تنظيف الهاتف ==="]
    lines.append(f"📦 المساحة قبل : {result['before_mb']} MB")
    lines.append(f"📦 المساحة بعد : {result['after_mb']} MB")
    lines.append(f"🗑️ تم تحرير   : {result['freed_mb']} MB ({result['freed_kb']} KB)")
    lines.append("─── التفاصيل ───")
    for detail in result["details"]:
        lines.append(
            f"  {detail['type']}: حذف {detail['removed']} عنصر — {detail['size_kb']} KB"
        )
    return {"status": "success", "intent": intent, "text": chr(10).join(lines)}


def handle_delete_file(orchestrator, intent, *, target=None, raw=None):
    try:
        from lab_v4_dev.core.safe_io import safe_delete
        target_path = target or getattr(orchestrator.context, "current_file", None)
        if not target_path:
            return {"status": "failed", "intent": intent, "message": "لم يتم تحديد الملف"}
        result = safe_delete(target_path, "user request")
        if result.get("status") == "success":
            text = f"تم حذف {target_path}"
            if result.get("audit_warning"):
                text += "، لكن تعذرت كتابة سجل التدقيق"
        else:
            text = result.get("message") or f"لم يتم حذف {target_path}"
        return {
            "status": result.get("status"),
            "intent": intent,
            "text": text,
            "backup": result.get("backup"),
            "snapshot": result.get("snapshot"),
            "audit_warning": result.get("audit_warning"),
        }
    except Exception as exc:
        return {"status": "failed", "intent": intent, "message": str(exc)}


__all__ = ["handle_clean", "handle_clean_device", "handle_delete_file"]
