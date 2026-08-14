"""
PIE-011A — Execution Transaction Manager

المسؤولية:
- إدارة دورة المعاملة أثناء التنفيذ.
"""


class ExecutionTransactionManager:

    def start(self, step):

        return {
            "status": "started",
            "step": step,
            "changes": [],
        }


    def commit(self, transaction):

        transaction["status"] = "committed"

        return transaction


    def rollback(self, transaction, reason):

        transaction["status"] = "rolled_back"
        transaction["reason"] = reason

        return transaction
