"""Local knowledge and capability handlers."""

def handle_capabilities(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.project_context import get_active_project as _gap
    from lab_v4_dev.awareness.project_memory import load_memory
    from lab_v4_dev.core.project_context import get_active_project as _gap
    _proj = _gap()
    _mem  = load_memory()
    _total = _mem.get("total_files", 0)
    _lines = [
        "=== CyberLab Agent ===",
        "",
        "فهم المشاريع: Python وTypeScript • الاعتماديات • نقاط الدخول • الملفات الحرجة",
        "تحليل الأخطاء: كشف • تحليل • إصلاح • تعلم تلقائي",
        "كتابة الكود: سكريبتات Python • تشغيل وتحليل",
        "الأمن السيبراني: شرح مفاهيم • حفظ محلي",
        "الذاكرة: حفظ الجلسات • سياق العمل",
        "",
        f"المشروع الحالي: {_proj.name} ({_total} ملف)",
    ]
    return {"status":"success","intent":intent,"source":"local",
            "text":"\n".join(_lines)}


def handle_save_kb(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.knowledge_base import store
    from lab_v4_dev.awareness.knowledge_base import store
    pending = getattr(orchestrator.context, "pending_save", None)
    last = orchestrator.context.last_result or {}
    topic = pending or last.get("pending_save")
    answer = last.get("text", "")
    if topic and answer:
        store(topic, answer, confirmed=True, confidence="EXPLICIT")
        orchestrator.context.pending_save = None
        return {"status":"success","intent":intent,
                "text":"✅ تم الحفظ في الذاكرة المحلية"}
    return {"status":"success","intent":intent,
            "text":"⚠️ لا يوجد شرح معلق للحفظ"}


def handle_skip_kb(orchestrator, intent, *, target=None, raw=None):
    orchestrator.context.pending_save = None
    return {"status":"success","intent":intent,
            "text":"⏭️ تم التجاوز — لن يُحفظ هذا الشرح"}


__all__ = ["handle_capabilities", "handle_save_kb", "handle_skip_kb"]
