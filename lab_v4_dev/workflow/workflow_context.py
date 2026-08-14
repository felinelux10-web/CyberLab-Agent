"""
Series 7 — Workflow Context

المسؤولية:
- حفظ سياق المهمة أثناء التنفيذ.
"""

from datetime import datetime


class WorkflowContext:

    def create(self, task):
        return {
            "task_id"   : task["id"],
            "task_name" : task["name"],
            "state"     : task["state"],
            "current"   : None,
            "completed" : [],
            "failed"    : [],
            "remaining" : task["steps"].copy(),
            "metadata"  : {},
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def update(self, context, key, value):
        context[key]          = value
        context["updated_at"] = datetime.now().isoformat()
        return context

    def set_current(self, context, step):
        context["current"]    = step
        context["updated_at"] = datetime.now().isoformat()
        return context
