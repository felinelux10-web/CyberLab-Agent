"""P013 canonical workflow task lifecycle object."""

from datetime import datetime
from typing import Any

from .workflow_state import WorkflowState


class WorkflowTask:
    """Owns workflow-level task identity and lifecycle state.

    This class does not execute actions. Low-level execution remains
    owned by the executor layer.
    """

    def __init__(self):
        self.state_machine = WorkflowState()

    def create(
        self,
        name: str,
        steps: list,
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        now = datetime.now().isoformat()

        return {
            "id": self._task_id(name, now),
            "name": name,
            "steps": list(steps),
            "priority": priority,
            "state": WorkflowState.PENDING,
            "metadata": dict(metadata or {}),
            "created_at": now,
            "updated_at": now,
        }

    def transition(self, task: dict, target: str) -> dict:
        if not isinstance(task, dict):
            raise TypeError("task must be a dict")

        current = task.get("state")

        result = self.state_machine.transition(current, target)

        if result["status"] != "ok":
            return result

        task["state"] = target
        task["updated_at"] = datetime.now().isoformat()

        return {
            "status": "ok",
            "state": target,
            "task": task,
        }

    def update_state(self, task: dict, state: str) -> dict:
        result = self.transition(task, state)

        if result["status"] != "ok":
            return task

        return result["task"]

    def is_terminal(self, task: dict) -> bool:
        return self.state_machine.is_terminal(task.get("state"))

    @staticmethod
    def _task_id(name: str, timestamp: str) -> str:
        import hashlib

        raw = f"{name}:{timestamp}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]
