"""
Series 8 — Runtime Lifecycle

المسؤولية:
- إدارة دورة حياة الـ Runtime.
- لا ينفذ أوامر.
- لا يعدل المشروع.
"""

from datetime import datetime


class RuntimeLifecycle:

    def __init__(self):
        self.state = "stopped"
        self.started_at = None

    def start(self):
        self.state = "running"
        self.started_at = datetime.now().isoformat()

    def pause(self):
        if self.state == "running":
            self.state = "paused"

    def resume(self):
        if self.state == "paused":
            self.state = "running"

    def stop(self):
        self.state = "stopped"

    def to_dict(self):
        return {
            "state": self.state,
            "started_at": self.started_at,
        }
