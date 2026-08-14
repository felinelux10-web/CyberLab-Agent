"""
PIE-008B — Simulation Decision Engine

المسؤولية:
- اتخاذ قرار بناءً على نتيجة المحاكاة.
"""


class SimulationDecisionEngine:

    def decide(self, simulation):

        decisions = []

        for item in simulation.get("results", []):

            status = item.get("simulation")

            if status == "needs_backup":
                action = "backup_required"

            elif status == "review_required":
                action = "manual_review"

            else:
                action = "allow"

            decisions.append({
                "file": item.get("file"),
                "action": action,
                "simulation": status,
            })

        return {
            "status": "decision_ready",
            "decisions": decisions,
        }
