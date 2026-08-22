from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lab_v4_dev.planner.decision_contracts import (
    ImpactAssessment,
    ImpactItem,
    PriorityAssessment,
    RiskAssessment,
)
from lab_v4_dev.planner.execution_decision import (
    ExecutionDecision,
    ExecutionDecisionEngine,
)
from lab_v4_dev.planner.impact_analyzer import ImpactAnalyzer
from lab_v4_dev.planner.priority_planner import PriorityPlanner
from lab_v4_dev.planner.risk_assessor import RiskAssessor


@dataclass(frozen=True)
class P10DecisionAssessment:
    """Canonical P010 decision assessment.

    This object contains only declarative planning information.
    It performs no execution, mutation, permission handling,
    snapshotting, or recovery.
    """

    impact: ImpactAssessment
    priority: tuple[PriorityAssessment, ...]
    risk: tuple[RiskAssessment, ...]
    decisions: tuple[ExecutionDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "impact": self.impact.to_dict(),
            "priority": [item.to_dict() for item in self.priority],
            "risk": [item.to_dict() for item in self.risk],
            "decisions": [item.to_dict() for item in self.decisions],
        }


class P10DecisionPipeline:
    """Canonical P010 Impact → Priority → Risk → Decision pipeline."""

    def __init__(
        self,
        impact_analyzer: ImpactAnalyzer | None = None,
        priority_planner: PriorityPlanner | None = None,
        risk_assessor: RiskAssessor | None = None,
        decision_engine: ExecutionDecisionEngine | None = None,
    ) -> None:
        self.impact_analyzer = impact_analyzer or ImpactAnalyzer()
        self.priority_planner = priority_planner or PriorityPlanner()
        self.risk_assessor = risk_assessor or RiskAssessor()
        self.decision_engine = decision_engine or ExecutionDecisionEngine()

    def assess(self, target: str) -> P10DecisionAssessment:
        impact = self.impact_analyzer.analyze(target)

        items = tuple(
            ImpactItem(
                file_path=path,
                level=(
                    "direct"
                    if path in impact.affected
                    else impact.level
                ),
                reason=impact.reason,
            )
            for path in impact.affected
        )

        if not items and impact.target:
            items = (
                ImpactItem(
                    file_path=impact.target,
                    level=impact.level,
                    reason=impact.reason,
                ),
            )

        priority = self.priority_planner.rank(items)
        risk = self.risk_assessor.assess(priority)
        decisions = self.decision_engine.decide(risk)

        return P10DecisionAssessment(
            impact=impact,
            priority=priority,
            risk=risk,
            decisions=decisions,
        )


__all__ = [
    "P10DecisionAssessment",
    "P10DecisionPipeline",
]
