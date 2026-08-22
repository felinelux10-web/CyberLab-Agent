from lab_v4_dev.planner.decision_contracts import ImpactAssessment
from lab_v4_dev.planner.impact_reasoning import (
    ImpactClassifier,
    ImpactReasoner,
)


def test_classifier_produces_structured_items():
    assessment = ImpactAssessment(
        target="target.py",
        affected=("direct.py", "indirect.py"),
        level="direct",
        reason="dependency impact analysis",
    )

    items = ImpactClassifier().classify(assessment)

    assert len(items) == 2
    assert items[0].file_path == "direct.py"
    assert items[0].level == "direct"
    assert items[1].file_path == "indirect.py"
    assert items[1].level == "indirect"


def test_reasoner_produces_explanations():
    assessment = ImpactAssessment(
        target="target.py",
        affected=("dependent.py",),
        level="direct",
        reason="dependency impact analysis",
    )

    items = ImpactClassifier().classify(assessment)
    explanations = ImpactReasoner().explain(assessment, items)

    assert explanations == (
        {
            "file": "dependent.py",
            "reason": "dependent.py depends on target.py",
            "impact_type": "dependency_change",
            "confidence": "high",
        },
    )
