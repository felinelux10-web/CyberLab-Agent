import pytest

from lab_v4_dev.planner.decision_contracts import (
    ImpactAssessment,
    PriorityAssessment,
    RiskAssessment,
)


def test_impact_assessment_is_structured():
    assessment = ImpactAssessment(
        target="a.py",
        affected=("b.py", "c.py"),
        level="direct",
        reason="dependency change",
    )

    assert assessment.affected_count == 2
    assert assessment.to_dict()["affected"] == ["b.py", "c.py"]


def test_priority_assessment_is_structured():
    assessment = PriorityAssessment(
        target="a.py",
        priority="critical",
        reason="direct impact",
    )

    assert assessment.to_dict() == {
        "target": "a.py",
        "priority": "critical",
        "reason": "direct impact",
    }


def test_risk_assessment_is_structured():
    assessment = RiskAssessment(
        target="a.py",
        risk="high",
        priority="critical",
        reason="critical change",
    )

    assert assessment.to_dict()["risk"] == "high"
    assert assessment.to_dict()["priority"] == "critical"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ImpactAssessment(
            target="a.py",
            level="invalid",
        ),
        lambda: PriorityAssessment(
            target="a.py",
            priority="invalid",
        ),
        lambda: RiskAssessment(
            target="a.py",
            risk="invalid",
            priority="critical",
        ),
    ],
)
def test_invalid_decision_levels_are_rejected(factory):
    with pytest.raises(ValueError):
        factory()


def test_risk_requires_valid_priority():
    with pytest.raises(ValueError):
        RiskAssessment(
            target="a.py",
            risk="high",
            priority="invalid",
        )
