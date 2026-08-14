"""
PIE-009B — Execution Audit Store

المسؤولية:
- حفظ واسترجاع سجل التدقيق.
"""

import json
from pathlib import Path


class ExecutionAuditStore:

    def __init__(self, path="execution_audit.json"):
        self.path = Path(path)

    def save(self, logs):

        self.path.write_text(
            json.dumps(
                logs,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        return {
            "status": "saved",
            "count": len(logs),
        }

    def load(self):

        if not self.path.exists():
            return []

        return json.loads(
            self.path.read_text(
                encoding="utf-8"
            )
        )
