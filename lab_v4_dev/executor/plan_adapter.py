from __future__ import annotations

from lab_v4_dev.planner.contracts import Plan, PlanStep
from lab_v4_dev.executor.contracts import ExecutionRequest


class PlanExecutionAdapter:
    """
    Translate a declarative P010 PlanStep into a canonical P011
    ExecutionRequest.

    This adapter performs contract translation only.
    It does not execute, validate permissions, or make planning decisions.
    """

    ACTION_MAP = {
        "shell": "run_command",
        "run_command": "run_command",
        "command": "run_command",
        "write_file": "write_file",
        "edit_file": "write_file",
    }

    def to_request(self, plan: Plan, step: PlanStep) -> ExecutionRequest:
        if not isinstance(plan, Plan):
            raise TypeError("plan must be a Plan instance")

        if not isinstance(step, PlanStep):
            raise TypeError("step must be a PlanStep instance")

        action = self.ACTION_MAP.get(step.action)
        if action is None:
            raise ValueError(
                f"unsupported planning action for execution: {step.action}"
            )

        parameters = dict(step.parameters)

        if action == "write_file":
            if "file" in parameters and "file_path" not in parameters:
                parameters["file_path"] = parameters.pop("file")

        return ExecutionRequest(
            plan_id=plan.plan_id or "p10-plan",
            step_id=step.step_id,
            action=action,
            parameters=parameters,
            metadata={
                "source": "p10_plan",
                "planning_action": step.action,
                "execution_schema": "p11.v1",
            },
        )


__all__ = ["PlanExecutionAdapter"]
