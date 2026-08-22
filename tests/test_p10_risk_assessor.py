from lab_v4_dev.planner.decision_contracts import (
    PriorityAssessment,
    RiskAssessment,
)
from lab_v4_dev.planner.risk_assessor import RiskAssessor


def test_critical_priority_becomes_high_risk():
    items = (
        PriorityAssessment(
            target="critical.py",
            priority="critical",
            reason="critical impact",
        ),
    )

    result = RiskAssessor().assess(items)

    assert result == (
        RiskAssessment(
            target="critical.py",
            risk="high",
            priority="critical",
            reason="critical impact",
        ),
    )


def test_risk_mapping_is_complete():
    items = (
        PriorityAssessment("critical.py", "critical"),
        PriorityAssessment("high.py", "high"),
        PriorityAssessment("medium.py", "medium"),
        PriorityAssessment("low.py", "low"),
    )

    result = RiskAssessor().assess(items)

    assert [item.risk for item in result] == [
        "high",
        "medium",
        "low",
        "minimal",
    ]


def test_priority_is_preserved():
    items = (
        PriorityAssessment(
            target="module.py",
            priority="high",
            reason="indirect dependency",
        ),
    )

    result = RiskAssessor().assess(items)

    assert result[0].priority == "high"
    assert result[0].target == "module.py"
    assert result[0].reason == "indirect dependency"


def test_empty_input_returns_empty_tuple():
    assert RiskAssessor().assess(()) == ()


def test_invalid_input_type_is_rejected():
    try:
        RiskAssessor().assess("not-a-list")
    except TypeError as exc:
        assert "items must be" in str(exc)
    else:
        raise AssertionError("invalid input must be rejected")


def test_invalid_item_type_is_rejected():
    try:
        RiskAssessor().assess(({"target": "x.py"},))
    except TypeError as exc:
        assert "PriorityAssessment" in str(exc)
    else:
        raise AssertionError("invalid item must be rejected")
