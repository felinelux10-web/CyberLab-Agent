"""
Series 7 — Workflow Cancel

المسؤولية:
- إلغاء المهمة بطريقة آمنة.
"""

from datetime import datetime


class WorkflowCancel:

    def can_cancel(self, context):
        return context.get("state") in ("running", "paused", "pending")

    def cancel(self, context, reason="user_request"):
        if not self.can_cancel(context):
            return {
                "status": "error",
                "reason": f"cannot cancel from state: {context.get('state')}",
            }
        context["state"]      = "cancelled"
        context["updated_at"] = datetime.now().isoformat()
        context.setdefault("metadata", {})["cancel_reason"] = reason
        return {"status": "cancelled", "reason": reason, "context": context}
