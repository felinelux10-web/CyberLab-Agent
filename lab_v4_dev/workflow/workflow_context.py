"""P013 canonical workflow execution context."""

from datetime import datetime


class WorkflowContext:
    """Runtime context for one workflow task.

    Context stores execution bookkeeping only. It does not execute steps
    and does not independently decide lifecycle transitions.
    """

    def create(self, task: dict) -> dict:
        if not isinstance(task, dict):
            raise TypeError("task must be a dict")

        now = datetime.now().isoformat()

        return {
            "task_id": task["id"],
            "task_name": task["name"],
            "state": task["state"],
            "current": None,
            "completed": [],
            "failed": [],
            "remaining": list(task.get("steps", [])),
            "metadata": dict(task.get("metadata", {})),
            "started_at": now,
            "updated_at": now,
        }

    def update(self, context: dict, key: str, value) -> dict:
        context[key] = value
        context["updated_at"] = datetime.now().isoformat()
        return context

    def set_current(self, context: dict, step) -> dict:
        return self.update(context, "current", step)

    def record_completed(self, context: dict, step) -> dict:
        context.setdefault("completed", []).append(step)

        if step in context.get("remaining", []):
            context["remaining"].remove(step)

        context["current"] = None
        context["updated_at"] = datetime.now().isoformat()

        return context

    def record_failed(self, context: dict, step, reason) -> dict:
        context.setdefault("failed", []).append({
            "step": step,
            "reason": reason,
        })

        context["current"] = None
        context["updated_at"] = datetime.now().isoformat()

        return context

    def snapshot(self, context: dict) -> dict:
        return {
            "task_id": context.get("task_id"),
            "task_name": context.get("task_name"),
            "state": context.get("state"),
            "current": context.get("current"),
            "completed": list(context.get("completed", [])),
            "failed": list(context.get("failed", [])),
            "remaining": list(context.get("remaining", [])),
            "metadata": dict(context.get("metadata", {})),
            "started_at": context.get("started_at"),
            "updated_at": context.get("updated_at"),
        }
