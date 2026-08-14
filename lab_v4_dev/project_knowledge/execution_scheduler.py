"""
PIE-006D — Execution Scheduler

المسؤولية:
- استخراج الخطوة التالية للتنفيذ.
"""


class ExecutionScheduler:

    def next_step(self, context):

        remaining = context.get(
            "remaining",
            []
        )

        if not remaining:

            return {
                "status": "finished",
                "step": None,
            }

        return {
            "status": "ready",
            "step": remaining[0],
        }
