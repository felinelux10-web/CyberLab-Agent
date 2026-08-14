"""
PIE-010A — Safe Execution Gate

المسؤولية:
- منع التنفيذ غير الآمن.
"""


class SafeExecutionGate:

    def check(self, simulation_decision):

        decisions = simulation_decision.get(
            "decisions",
            []
        )

        for item in decisions:

            action = item.get("action")

            if action == "backup_required":
                return {
                    "status": "blocked",
                    "reason": "backup_required",
                    "file": item.get("file"),
                }

            if action == "manual_review":
                return {
                    "status": "blocked",
                    "reason": "manual_review",
                    "file": item.get("file"),
                }

        return {
            "status": "allowed",
            "reason": "safe",
        }
