"""
Series 7 — Workflow Executor

المسؤولية:
- تنفيذ المهمة خطوة بخطوة.
"""

from datetime import datetime


class WorkflowExecutor:

    def execute_step(self, context, step):
        remaining = context.get("remaining", [])
        if step in remaining:
            remaining.remove(step)
        context["current"]    = step
        context["updated_at"] = datetime.now().isoformat()
        return {
            "status" : "executed",
            "step"   : step,
            "context": context,
        }

    def complete_step(self, context, step):
        context["completed"].append(step)
        context["current"]    = None
        context["updated_at"] = datetime.now().isoformat()
        if not context.get("remaining"):
            context["state"] = "completed"
        return context

    def fail_step(self, context, step, reason):
        context["failed"].append({"step": step, "reason": reason})
        context["current"]    = None
        context["updated_at"] = datetime.now().isoformat()
        context["state"]      = "failed"
        return context
