"""
PIE-010B — Execution Permission Manager

المسؤولية:
- إدارة صلاحية التنفيذ.
"""


class ExecutionPermissionManager:

    def check(self, gate_result):

        status = gate_result.get(
            "status"
        )

        if status == "allowed":
            return {
                "permission": "granted",
                "execute": True,
            }

        return {
            "permission": "denied",
            "execute": False,
            "reason": gate_result.get(
                "reason"
            ),
        }
