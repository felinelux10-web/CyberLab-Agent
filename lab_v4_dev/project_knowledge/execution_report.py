"""
PIE-006E — Execution Report

المسؤولية:
- إنشاء تقرير نهائي لخطة التنفيذ.
"""


class ExecutionReport:

    def build(self, plan):

        return {
            "target": plan["target"],
            "impacted_count": len(plan["impacted"]),
            "priority_count": len(plan["priority"]),
            "decision_status": plan["decision"]["status"],
            "validation": plan["validation"]["valid"],
            "next_step": plan["next_step"]["status"],

            "permission": plan.get("permission"),
            "transaction": plan.get("transaction"),
            "execution_result": plan.get("execution_result"),
            "recovery": plan.get("recovery"),
            "audit": plan.get("audit"),
        }
