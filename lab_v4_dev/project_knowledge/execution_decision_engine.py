"""
PIE-005A — Execution Decision Engine

المسؤولية:
- اتخاذ قرار حول كيفية تنفيذ الخطة.
- تحديد مستوى الأمان قبل التنفيذ.
- تحويل خطة التنفيذ إلى قرار نهائي.

لا يقوم بـ:
- تنفيذ التعديلات.
- تحليل العلاقات.
"""

from .risk_assessor import RiskAssessor


class ExecutionDecisionEngine:

    def decide(self, execution_plan):

        risks = RiskAssessor().assess(
            execution_plan
        )

        decisions = []

        for step, risk_info in zip(
            execution_plan,
            risks
        ):

            priority = step.get("priority")
            risk = risk_info["risk"]

            if priority == "critical":
                action = "auto_apply"

            elif priority == "high":
                action = "require_review"

            elif priority == "medium":
                action = "simulate_first"

            else:
                action = "ignore"

            decisions.append({
                "file": step.get("file"),
                "action": action,
                "reason": step.get("reason"),
                "priority": priority,
                "risk": risk
            })

        return {
            "decisions": decisions,
            "status": "decision_ready"
        }
