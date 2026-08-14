"""
Series 8 — Runtime Monitor

المسؤولية:
- مراقبة حالة الـ Runtime.
- لا ينفذ أوامر.
- لا يعدل المشروع.
"""

from datetime import datetime


class RuntimeMonitor:

    def __init__(self):
        self.last_check = None
        self.health = "unknown"

    def check(self):
        self.last_check = datetime.now().isoformat()
        self.health = "ok"

    def to_dict(self):
        return {
            "health": self.health,
            "last_check": self.last_check,
        }
