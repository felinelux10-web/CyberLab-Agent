from __future__ import annotations

from typing import Any

from lab_v4_dev.planner.decision_contracts import RiskAssessment


DECISION_LEVELS = (
    "auto_apply",
    "require_review",
    "simulate_first",
    "ignore",
)


class ExecutionDecision:
    """Immutable-style declarative execution decision."""

    def __init__(
        self,
        target: str,
        action: str,
        priority: str,
        risk: str,
        reason: str = "",
    ) -> None:
        if not target:
            raise ValueError("target must not be empty")

        if action not in DECISION_LEVELS:
            raise ValueError(f"invalid decision action: {action}")

        self.target = target
        self.action = action
        self.priority = priority
        self.risk = risk
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "action": self.action,
            "priority": self.priority,
            "risk": self.risk,
            "reason": self.reason,
        }


class ExecutionDecisionEngine:
    """
    Convert validated risk assessments into declarative decisions.

    This layer does NOT:
    - execute anything
    - mutate files
    - create snapshots
    - perform recovery
    - bypass validation
    """

    ACTION_BY_PRIORITY = {
        "critical": "auto_apply",
        "high": "require_review",
        "medium": "simulate_first",
        "low": "ignore",
    }

    def decide(
        self,
        assessments: tuple[RiskAssessment, ...]
        | list[RiskAssessment],
    ) -> tuple[ExecutionDecision, ...]:

        decisions: list[ExecutionDecision] = []

        for assessment in assessments:
            if not isinstance(assessment, RiskAssessment):
                raise TypeError(
                    "assessments must contain RiskAssessment objects"
                )

            action = self.ACTION_BY_PRIORITY[assessment.priority]

            decisions.append(
                ExecutionDecision(
                    target=assessment.target,
                    action=action,
                    priority=assessment.priority,
                    risk=assessment.risk,
                    reason=assessment.reason,
                )
            )

        return tuple(decisions)


__all__ = [
    "DECISION_LEVELS",
    "ExecutionDecision",
    "ExecutionDecisionEngine",
]
