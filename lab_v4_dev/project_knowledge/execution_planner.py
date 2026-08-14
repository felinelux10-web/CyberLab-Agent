"""
PIE-004C — Execution Planner

المسؤولية:
- تحويل الأولويات إلى خطة تنفيذ.
- ترتيب خطوات التنفيذ.
- لا يقوم بأي تعديل فعلي.
"""


class ExecutionPlanner:

    PRIORITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    ACTION_MAP = {
        "critical": "modify",
        "high": "review",
        "medium": "verify",
        "low": "ignore",
    }

    def create_execution_plan(self, priority_items):

        ordered = sorted(
            priority_items,
            key=lambda item: self.PRIORITY_ORDER.get(
                item["priority"],
                99
            )
        )

        plan = []

        for index, item in enumerate(ordered, start=1):

            plan.append(
                {
                    "step": index,
                    "file": item["file"],
                    "priority": item["priority"],
                    "action": self.ACTION_MAP.get(
                        item["priority"],
                        "review"
                    ),
                    "reason": item["reason"],
                }
            )

        return plan

