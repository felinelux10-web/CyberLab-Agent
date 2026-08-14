"""
Series 7 — Workflow Scheduler

المسؤولية:
- اختيار المهمة التالية من الطابور.
- استخراج الخطوة التالية من السياق.
"""


class WorkflowScheduler:

    PRIORITY_ORDER = {
        "critical": 0,
        "high"    : 1,
        "normal"  : 2,
        "low"     : 3,
    }

    def next_task(self, queue):
        if queue.is_empty():
            return {"status": "empty", "task": None}
        return {"status": "ready", "task": queue.dequeue()}

    def next_step(self, context):
        remaining = context.get("remaining", [])
        if not remaining:
            return {"status": "finished", "step": None}
        return {"status": "ready", "step": remaining[0]}

    def prioritize(self, tasks):
        return sorted(
            tasks,
            key=lambda t: self.PRIORITY_ORDER.get(
                t.get("priority", "normal"), 2
            )
        )
