"""
Series 7 — Workflow Report

المسؤولية:
- إنتاج تقرير كامل عن المهمة.
"""

from datetime import datetime


class WorkflowReport:

    def build(self, context, logger):
        return {
            "status"    : "report_ready",
            "task_id"   : context.get("task_id"),
            "task_name" : context.get("task_name"),
            "state"     : context.get("state"),
            "completed" : len(context.get("completed", [])),
            "failed"    : len(context.get("failed", [])),
            "remaining" : len(context.get("remaining", [])),
            "events"    : len(logger.get_events()),
            "generated" : datetime.now().isoformat(),
        }
