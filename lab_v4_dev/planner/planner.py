from __future__ import annotations

from typing import Any

from lab_v4_dev.planner.decision_pipeline import P10DecisionPipeline

from lab_v4_dev.planner.contracts import Plan, PlanStep


class Planner:
    def __init__(self, *args, **kwargs):
        self.decision_pipeline = P10DecisionPipeline()


    """
    Declarative planning subsystem.

    Planner converts an intent into a reviewable Plan.
    It MUST NOT execute commands, mutate files, manage permissions,
    create snapshots, or perform recovery.
    """

    def assess_decision(self, target: str):
        """Return the canonical P010 decision assessment for a target.

        This is declarative only. Execution remains outside Planner.
        """
        return self.decision_pipeline.assess(target)

    def plan(
        self,
        intent: dict[str, Any],
        steps: list[PlanStep] | tuple[PlanStep, ...],
        *,
        plan_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Plan:
        if not isinstance(intent, dict):
            raise TypeError("intent must be a dict")

        normalized_steps = tuple(steps)

        return Plan(
            plan_id=plan_id,
            intent=dict(intent),
            steps=normalized_steps,
            metadata=dict(metadata or {}),
        )

    def from_actions(
        self,
        intent: dict[str, Any],
        actions: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        *,
        plan_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Plan:
        """
        Convert declarative action descriptions into the Plan contract.

        This method performs no execution.
        """
        steps = tuple(
            PlanStep(
                step_id=action["step_id"],
                action=action["action"],
                parameters=dict(action.get("parameters", {})),
                depends_on=tuple(action.get("depends_on", ())),
                description=action.get("description", ""),
            )
            for action in actions
        )

        return self.plan(
            intent,
            steps,
            plan_id=plan_id,
            metadata=metadata,
        )


__all__ = ["Planner"]
