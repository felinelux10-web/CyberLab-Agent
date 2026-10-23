from __future__ import annotations

from lab_v4_dev.planner.contracts import Plan, PlanStep
from lab_v4_dev.executor.contracts import ExecutionRequest
from lab_v4_dev.intent.risk_levels import get_risk


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

        intent = plan.intent
        if isinstance(intent, dict):
            intent = intent.get("intent") or intent.get("action")
        risk_level = get_risk(intent)
        if risk_level == "unreliable" and action == "write_file":
            risk_level = "safe_write"

        metadata = {
            "source": "p10_plan",
            "planning_action": step.action,
            "execution_schema": "p11.v1",
            "risk_level": risk_level,
        }
        if risk_level == "safe_write":
            metadata["write_policy"] = "safe_write"
        if isinstance(plan.metadata, dict):
            approval = plan.metadata.get("approval")
            if approval is not None:
                metadata["approval"] = approval

        return ExecutionRequest(
            plan_id=plan.plan_id or "p10-plan",
            step_id=step.step_id,
            action=action,
            parameters=parameters,
            metadata=metadata,
        )


__all__ = ["PlanExecutionAdapter"]
