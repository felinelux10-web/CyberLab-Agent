"""
Series 8 — Runtime State

المسؤولية:
- الاحتفاظ بالحالة الحالية للـ Runtime.
- عدم تنفيذ أي منطق.
- عدم التعامل مع الملفات.
- يمثل الحالة الحية أثناء التشغيل فقط.
"""


class RuntimeState:

    def __init__(self):
        self.status = "idle"
        self.current_operation = None
        self.current_project = None
        self.started_at = None
        self.updated_at = None

    def begin(self, operation: str, project: str = None):
        from datetime import datetime
        self.status = "running"
        self.current_operation = operation
        self.current_project = project
        self.started_at = datetime.now().isoformat()
        self.updated_at = self.started_at

    def end(self):
        from datetime import datetime
        self.status = "idle"
        self.current_operation = None
        self.updated_at = datetime.now().isoformat()

    def to_dict(self):
        return {
            "status": self.status,
            "current_operation": self.current_operation,
            "current_project": self.current_project,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }
