"""Planning-only code change handlers."""


def handle_cleanup_code(orchestrator, intent, *, target=None, raw=None):
    import uuid
    from lab_v4_dev.planner.planner import Planner

    scope = str(target or "").strip()
    plan = Planner().from_actions(
        {
            "action": getattr(intent, "value", intent),
            "target": scope or None,
        },
        [
            {
                "step_id": "step-1",
                "action": "confirm_scope",
                "parameters": {"target": scope or None},
                "description": "تأكيد ملف/مجلد ونطاق التنظيف المطلوب",
            },
            {
                "step_id": "step-2",
                "action": "prepare_reviewable_proposal",
                "parameters": {
                    "target": scope or None,
                    "requires_user_review": True,
                },
                "depends_on": ["step-1"],
                "description": "إعداد مقترح قابل للمراجعة دون تطبيقه",
            },
        ],
        plan_id=f"cleanup-code-{uuid.uuid4().hex}",
        metadata={
            "execution_status": "not_started",
            "mutates_files": False,
            "user_review_required": True,
        },
    )
    if scope:
        message = (
            f"أعددت خطة مراجعة مبدئية للنطاق {scope}. هذه خطة فقط؛ "
            "لم يُعدّل أو يُحذف أي ملف. حدّد قواعد التنظيف المطلوبة "
            "أو اطلب مراجعة النطاق للمتابعة."
        )
    else:
        message = (
            "تنظيف الكود يتطلب تحديد مسار ملف/مجلد أو نطاق واضح قبل إعداد "
            "مقترح قابل للمراجعة. الخطة المرفقة مبدئية فقط؛ لم يُعدّل "
            "أو يُحذف أي ملف."
        )
    return {
        "status": "needs_clarification",
        "intent": intent,
        "target": scope or "",
        "text": message,
        "plan": plan.to_dict(),
        "plan_only": True,
        "executed": False,
    }


def handle_plan_change(orchestrator, intent, *, target=None, raw=None):
    import os
    import re as _re_pie
    m = _re_pie.search(r'[\w./]+\.py', raw)
    if not m:
        return {"status":"needs_clarification","intent":intent,
                "text":"أي ملف تريد تخطيط تعديله؟ مثال: خطط لتعديل core/agent.py"}
    target_file = m.group(0)
    try:
        from lab_v4_dev.project_knowledge.analysis_engine import AnalysisEngine
        from lab_v4_dev.dni.knowledge_router import create_p10_plan_from_change

        engine = AnalysisEngine()
        if os.path.exists(target_file):
            engine.analyze_file(target_file)

        plan = create_p10_plan_from_change(
            target_file,
            plan_id=f"pie-{target_file}",
            metadata={"source": "orchestrator.plan_change"},
        )

        impacted = [
            step.parameters.get("file")
            for step in plan.steps
            if step.parameters.get("file")
        ]
        exec_plan = plan.steps
        lines = ["خطة تعديل " + target_file + ":"]
        if impacted:
            lines.append("الملفات المتأثرة (" + str(len(impacted)) + "):")
            for f2 in impacted[:5]:
                lines.append("  ⚠️  " + f2)
        else:
            lines.append("✅ لا توجد ملفات متأثرة مباشرة")
        if exec_plan:
            lines.append("خطوات التنفيذ (" + str(len(exec_plan)) + "):")
            for index, step in enumerate(exec_plan[:3], start=1):
                file_path = step.parameters.get("file", "")
                priority = step.parameters.get("priority", "")
                lines.append(
                    "  [" + str(index) + "] "
                    + file_path
                    + " — "
                    + step.action
                    + " (" + priority + ")"
                )
        lines.append("ℹ️ هذه خطة معاينة فقط — لا يتم أي تعديل حتى الآن.")
        return {"status":"success","intent":intent,"source":"pie",
                "text":"\n".join(lines)}
    except Exception as _e_pie:
        return {"status":"failed","intent":intent,
                "text":"خطأ في PIE: " + str(_e_pie)}


__all__ = ["handle_cleanup_code", "handle_plan_change"]
