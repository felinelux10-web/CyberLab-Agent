"""
PIE-007B — Execution State Manager

المسؤولية:
- تحديث حالة التنفيذ أثناء التشغيل.
"""


class ExecutionStateManager:

    def advance(self, context):

        remaining = context.get("remaining", [])

        if not remaining:
            context["status"] = "finished"
            return context

        step = remaining.pop(0)

        context["completed"].append(step)

        context["current_step"] = (
            remaining[0] if remaining else None
        )

        if not remaining:
            context["status"] = "finished"

        return context
