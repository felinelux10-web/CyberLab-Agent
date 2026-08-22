from __future__ import annotations

from lab_v4_dev.planner.decision_contracts import (
    ImpactItem,
    PriorityAssessment,
)


class PriorityPlanner:
    """
    Declarative priority planning.

    Converts impact classifications into explicit priority assessments.

    This layer MUST NOT:
    - execute anything
    - mutate files
    - inspect permissions
    - assess execution risk
    - create snapshots
    - perform recovery
    """

    PRIORITY_BY_IMPACT = {
        "direct": "critical",
        "indirect": "high",
        "possible": "medium",
        "unknown": "low",
    }

    ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def rank(
        self,
        items: tuple[ImpactItem, ...] | list[ImpactItem],
    ) -> tuple[PriorityAssessment, ...]:
        if not isinstance(items, (tuple, list)):
            raise TypeError("items must be a tuple or list")

        assessments = []

        for item in items:
            if not isinstance(item, ImpactItem):
                raise TypeError("items must contain ImpactItem objects")

            priority = self.PRIORITY_BY_IMPACT[item.level]

            assessments.append(
                PriorityAssessment(
                    target=item.file_path,
                    priority=priority,
                    reason=item.reason,
                )
            )

        assessments.sort(
            key=lambda item: self.ORDER[item.priority]
        )

        return tuple(assessments)


__all__ = ["PriorityPlanner"]
