from __future__ import annotations

from typing import Any

from lab_v4_dev.planner.contracts import Plan, PlanStep


class LegacyExecutionPlanAdapter:
    """Convert the legacy execution_plan representation into P10 Plan."""

    def convert(
        self,
        intent: dict[str, Any],
        execution_plan: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        *,
        plan_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Plan:
        if not isinstance(intent, dict):
            raise TypeError("intent must be a dict")

        if not isinstance(execution_plan, (list, tuple)):
            raise TypeError("execution_plan must be a list or tuple")

        steps = []

        for index, item in enumerate(execution_plan, start=1):
            if not isinstance(item, dict):
                raise TypeError("execution_plan items must be dicts")

            file_path = item.get("file")
            if not file_path:
                raise ValueError("execution_plan item must contain file")

            legacy_action = item.get("action", "review")

            steps.append(
                PlanStep(
                    step_id=f"step-{index}",
                    action=legacy_action,
                    parameters={
                        "file": file_path,
                        "priority": item.get("priority", "low"),
                    },
                    description=item.get("reason", ""),
                )
            )

        return Plan(
            plan_id=plan_id,
            intent=dict(intent),
            steps=tuple(steps),
            metadata=dict(metadata or {}),
        )


__all__ = ["LegacyExecutionPlanAdapter"]
