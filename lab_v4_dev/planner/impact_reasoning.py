from __future__ import annotations

from lab_v4_dev.planner.decision_contracts import (
    ImpactAssessment,
    ImpactItem,
)


class ImpactClassifier:
    """Classifies affected components without executing or mutating."""

    def classify(self, assessment: ImpactAssessment) -> tuple[ImpactItem, ...]:
        if not isinstance(assessment, ImpactAssessment):
            raise TypeError("assessment must be an ImpactAssessment")

        return tuple(
            ImpactItem(
                file_path=file_path,
                level="direct" if index == 0 else "indirect",
                reason="depends on changed component",
            )
            for index, file_path in enumerate(assessment.affected)
        )


class ImpactReasoner:
    """Produces deterministic explanations for classified impact."""

    def explain(
        self,
        assessment: ImpactAssessment,
        items: tuple[ImpactItem, ...] | list[ImpactItem],
    ) -> tuple[dict[str, str], ...]:
        if not isinstance(assessment, ImpactAssessment):
            raise TypeError("assessment must be an ImpactAssessment")

        return tuple(
            {
                "file": item.file_path,
                "reason": (
                    f"{item.file_path} depends on "
                    f"{assessment.target}"
                ),
                "impact_type": "dependency_change",
                "confidence": "high",
            }
            for item in items
        )


__all__ = ["ImpactClassifier", "ImpactReasoner"]
