"""
Series 7 — Workflow Task

المسؤولية:
- تمثيل المهمة كوحدة مستقلة.
"""

import uuid
from datetime import datetime


class WorkflowTask:

    def create(self, name, steps, priority="normal"):
        return {
            "id"        : str(uuid.uuid4())[:8],
            "name"      : name,
            "priority"  : priority,
            "state"     : "pending",
            "steps"     : steps,
            "completed" : [],
            "failed"    : [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def update_state(self, task, state):
        task["state"]      = state
        task["updated_at"] = datetime.now().isoformat()
        return task
