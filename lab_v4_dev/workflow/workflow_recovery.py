"""
Series 7 — Workflow Recovery

المسؤولية:
- استرجاع التنفيذ عند الفشل.
"""

from datetime import datetime
from lab_v4_dev.core.audit import emit_event


class WorkflowRecovery:

    MAX_RETRIES = 3

    def handle(self, context, step, reason):
        retries = context.get("metadata", {}).get("retries", {})
        step_key = step.get("name", str(step))
        count = retries.get(step_key, 0)

        # Emit event for recovery decision start
        emit_event("workflow_recovery.decision", source="workflow_recovery", context={"step": step_key, "retries": count}, details={"reason": reason})

        if count >= self.MAX_RETRIES:
            result = {
                "action": "abort",
                "reason": f"max retries reached for {step_key}",
                "context": context,
            }
            emit_event("workflow_recovery.abort", source="workflow_recovery", context={"step": step_key}, details={"reason": result["reason"]})
            return result

        retries[step_key] = count + 1
        context.setdefault("metadata", {})["retries"] = retries
        context["state"] = "running"
        context["updated_at"] = datetime.now().isoformat()

        result = {
            "action": "retry",
            "attempt": count + 1,
            "step": step,
            "context": context,
        }

        emit_event("workflow_recovery.retry", source="workflow_recovery", context={"step": step_key}, details={"attempt": result["attempt"]})
        return result
