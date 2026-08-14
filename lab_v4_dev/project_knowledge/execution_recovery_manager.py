"""
PIE-007C — Execution Recovery Manager

المسؤولية:
- إدارة حالة الفشل.
- تحديد قرار الاستمرار أو التوقف.
"""


class ExecutionRecoveryManager:

    def handle_failure(self, context, step):

        context["failed"].append(step)

        if step.get("priority") == "critical":
            context["status"] = "halted"
            action = "stop"

        else:
            action = "continue"

        return {
            "status": context["status"],
            "action": action,
            "failed_step": step,
            "context": context,
        }
