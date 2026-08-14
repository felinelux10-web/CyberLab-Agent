"""
Series 8 — Runtime Context

المسؤولية:
- حفظ سياق التشغيل الحالي.
- لا يقوم بالتنفيذ.
- لا يقرأ أو يكتب ملفات.
"""


class RuntimeContext:

    def __init__(self):
        self.project = None
        self.goal = None
        self.phase = None
        self.active_module = None
        self.active_file = None

    def update(self, project=None, goal=None, phase=None,
               active_module=None, active_file=None):
        if project is not None:
            self.project = project
        if goal is not None:
            self.goal = goal
        if phase is not None:
            self.phase = phase
        if active_module is not None:
            self.active_module = active_module
        if active_file is not None:
            self.active_file = active_file

    def reset(self):
        self.project = None
        self.goal = None
        self.phase = None
        self.active_module = None
        self.active_file = None

    def to_dict(self):
        return {
            "project": self.project,
            "goal": self.goal,
            "phase": self.phase,
            "active_module": self.active_module,
            "active_file": self.active_file,
        }
