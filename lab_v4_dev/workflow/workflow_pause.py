"""
Series 7 — Workflow Pause

المسؤولية:
- إيقاف المهمة مؤقتاً بطريقة آمنة.
"""

from datetime import datetime


class WorkflowPause:

    def can_pause(self, context):
        return context.get("state") == "running"

    def pause(self, context):
        if not self.can_pause(context):
            return {
                "status" : "error",
                "reason" : f"cannot pause from state: {context.get('state')}",
            }
        context["state"]      = "paused"
        context["updated_at"] = datetime.now().isoformat()
        return {"status": "paused", "context": context}
