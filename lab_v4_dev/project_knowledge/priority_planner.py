"""
PIE-004B — Priority Planner

المسؤولية:
- ترتيب الملفات حسب أولوية التنفيذ.

لا يقوم بـ:
- تحليل الملفات.
- تنفيذ التعديلات.
- تعديل قاعدة المعرفة.
"""


class PriorityPlanner:

    PRIORITY = {
        "direct": "critical",
        "indirect": "high",
        "possible": "medium",
        "unknown": "low",
    }

    def rank(self, classified):

        ranked = []

        for item in classified:

            ranked.append(
                {
                    "file": item["file"],
                    "priority": self.PRIORITY.get(
                        item.get("level", "unknown"),
                        "low",
                    ),
                    "reason": item["reason"],
                }
            )

        order = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }

        ranked.sort(
            key=lambda x: order[x["priority"]]
        )

        return ranked
