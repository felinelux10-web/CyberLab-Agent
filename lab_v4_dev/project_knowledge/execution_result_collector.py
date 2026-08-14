"""
PIE-012 — Execution Result Collector

المسؤولية:
- جمع نتيجة التنفيذ.
"""


class ExecutionResultCollector:

    def collect(self, transaction, result):

        return {
            "transaction_status": transaction.get(
                "status"
            ),
            "result": result,
            "collected": True,
        }
