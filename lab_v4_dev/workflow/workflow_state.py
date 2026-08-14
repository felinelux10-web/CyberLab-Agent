"""
Series 7 — Workflow State

المسؤولية:
- تعريف حالات دورة حياة المهمة.
- إدارة الانتقال بين الحالات.
"""


class WorkflowState:

    PENDING   = "pending"
    RUNNING   = "running"
    PAUSED    = "paused"
    CANCELLED = "cancelled"
    FAILED    = "failed"
    COMPLETED = "completed"

    TRANSITIONS = {
        PENDING   : [RUNNING, CANCELLED],
        RUNNING   : [PAUSED, FAILED, COMPLETED, CANCELLED],
        PAUSED    : [RUNNING, CANCELLED],
        FAILED    : [RUNNING],
        COMPLETED : [],
        CANCELLED : [],
    }

    def can_transition(self, current, target):
        return target in self.TRANSITIONS.get(current, [])

    def transition(self, current, target):
        if not self.can_transition(current, target):
            return {
                "status": "error",
                "reason": f"cannot transition from {current} to {target}",
            }
        return {
            "status": "ok",
            "state": target,
        }
