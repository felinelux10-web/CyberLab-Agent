"""

from .execution_audit_store import ExecutionAuditStore
PIE-009A — Execution Audit Logger

المسؤولية:
- تسجيل أحداث دورة التنفيذ.
"""

from .execution_audit_store import ExecutionAuditStore


class ExecutionAuditLogger:

    def __init__(self, fresh=True):
        self.store = ExecutionAuditStore()
        self.logs = [] if fresh else self.store.load()

    def record(self, event, data):

        self.logs.append({
            "event": event,
            "data": data,
        })

        self.store.save(
            self.logs
        )

        return {
            "status": "recorded",
            "count": len(self.logs),
        }

    def get_logs(self):

        return self.logs
