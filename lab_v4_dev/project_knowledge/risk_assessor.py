"""
PIE-005B — Risk Assessor

المسؤولية:
- تقييم مخاطر تنفيذ التعديل.
- إنتاج مستوى خطورة موحد.
"""


class RiskAssessor:

    def assess(self, execution_plan):

        result = []

        for step in execution_plan:

            priority = step["priority"]

            if priority == "critical":
                risk = "high"

            elif priority == "high":
                risk = "medium"

            elif priority == "medium":
                risk = "low"

            else:
                risk = "minimal"

            result.append(
                {
                    "file": step["file"],
                    "risk": risk,
                    "priority": priority,
                    "action": step["action"],
                }
            )

        return result
