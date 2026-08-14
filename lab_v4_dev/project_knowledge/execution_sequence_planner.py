"""
PIE-006A — Execution Sequence Planner

المسؤولية:
- ترتيب خطوات التنفيذ.
- إنتاج Execution Sequence.

لا يقوم بـ:
- تنفيذ التعديلات.
- اتخاذ القرار.
"""


class ExecutionSequencePlanner:

    PRIORITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def build(self, execution_plan):

        ordered = sorted(
            execution_plan,
            key=lambda item: self.PRIORITY_ORDER.get(
                item.get("priority"),
                99
            )
        )

        sequence = []

        for index, item in enumerate(ordered, start=1):

            sequence.append(
                {
                    "order": index,
                    **item
                }
            )

        return sequence
