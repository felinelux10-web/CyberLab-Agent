"""
Series 7 — Workflow Recovery

المسؤولية:
- استرجاع التنفيذ عند الفشل.
"""

from datetime import datetime


class WorkflowRecovery:

    MAX_RETRIES = 3

    def handle(self, context, step, reason):
        retries = context.get("metadata", {}).get("retries", {})
        step_key = step.get("name", str(step))
        count = retries.get(step_key, 0)

        if count >= self.MAX_RETRIES:
            return {
                "action" : "abort",
                "reason" : f"max retries reached for {step_key}",
                "context": context,
            }

        retries[step_key] = count + 1
        context.setdefault("metadata", {})["retries"] = retries
        context["state"]      = "running"
        context["updated_at"] = datetime.now().isoformat()

        return {
            "action" : "retry",
            "attempt": count + 1,
            "step"   : step,
            "context": context,
        }
