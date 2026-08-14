"""
Series 8 — Runtime Snapshot

المسؤولية:
- حفظ لقطة من حالة الـ Runtime.
"""

from datetime import datetime


class RuntimeSnapshot:

    def __init__(self):
        self.created_at = None
        self.snapshot = {}

    def capture(self, data: dict):
        self.created_at = datetime.now().isoformat()
        self.snapshot = dict(data)

    def to_dict(self):
        return {
            "created_at": self.created_at,
            "snapshot": self.snapshot,
        }
