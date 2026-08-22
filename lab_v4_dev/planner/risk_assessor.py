from __future__ import annotations

from lab_v4_dev.planner.decision_contracts import (
    PriorityAssessment,
    RiskAssessment,
)


class RiskAssessor:
    """
    Declarative risk assessment.

    Converts priority assessments into normalized risk assessments.

    This layer MUST NOT:
    - execute anything
    - mutate files
    - inspect permissions
    - create snapshots
    - perform recovery
    - make execution decisions
    """

    RISK_BY_PRIORITY = {
        "critical": "high",
        "high": "medium",
        "medium": "low",
        "low": "minimal",
    }

    def assess(
        self,
        items: tuple[PriorityAssessment, ...]
        | list[PriorityAssessment],
    ) -> tuple[RiskAssessment, ...]:
        if not isinstance(items, (tuple, list)):
            raise TypeError("items must be a tuple or list")

        assessments = []

        for item in items:
            if not isinstance(item, PriorityAssessment):
                raise TypeError(
                    "items must contain PriorityAssessment objects"
                )

            risk = self.RISK_BY_PRIORITY[item.priority]

            assessments.append(
                RiskAssessment(
                    target=item.target,
                    risk=risk,
                    priority=item.priority,
                    reason=item.reason,
                )
            )

        return tuple(assessments)


__all__ = ["RiskAssessor"]
