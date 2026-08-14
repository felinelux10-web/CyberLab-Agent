"""
PIE-011B — Transaction Recovery Controller

المسؤولية:
- التحكم في استرجاع المعاملات.
"""


class TransactionRecoveryController:

    def recover(self, transaction, error):

        transaction["status"] = "rolled_back"

        transaction["recovery"] = {
            "status": "completed",
            "reason": error,
        }

        return transaction
