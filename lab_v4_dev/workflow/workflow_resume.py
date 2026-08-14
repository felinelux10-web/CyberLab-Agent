"""
Series 7 — Workflow Resume

المسؤولية:
- استكمال مهمة متوقفة من آخر نقطة.
"""

from datetime import datetime


class WorkflowResume:

    def can_resume(self, context):
        state = context.get("state")
        return state in ("paused", "failed")

    def resume(self, context):
        if not self.can_resume(context):
            return {
                "status" : "error",
                "reason" : f"cannot resume from state: {context.get('state')}",
                "context": context,
            }

        context["state"]      = "running"
        context["updated_at"] = datetime.now().isoformat()

        return {
            "status"  : "resumed",
            "current" : context.get("current"),
            "remaining": len(context.get("remaining", [])),
            "context" : context,
        }
