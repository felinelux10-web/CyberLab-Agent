"""
Series 7 — Workflow Logger

المسؤولية:
- تسجيل أحداث دورة حياة المهمة.
"""

from datetime import datetime


class WorkflowLogger:

    def __init__(self):
        self.events = []

    def log(self, event, data=None):
        self.events.append({
            "event"    : event,
            "data"     : data or {},
            "timestamp": datetime.now().isoformat(),
        })
        return {"status": "logged", "count": len(self.events)}

    def get_events(self):
        return self.events

    def clear(self):
        self.events = []
