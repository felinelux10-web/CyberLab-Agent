from lab_v4_dev.planner.decision_contracts import RiskAssessment
from lab_v4_dev.planner.execution_decision import (
    ExecutionDecision,
    ExecutionDecisionEngine,
)


def test_execution_decision_is_structured():
    decision = ExecutionDecision(
        target="a.py",
        action="require_review",
        priority="high",
        risk="medium",
        reason="review required",
    )

    assert decision.to_dict() == {
        "target": "a.py",
        "action": "require_review",
        "priority": "high",
        "risk": "medium",
        "reason": "review required",
    }


def test_execution_decision_rejects_invalid_action():
    try:
        ExecutionDecision(
            target="a.py",
            action="execute_now",
            priority="high",
            risk="medium",
        )
    except ValueError as exc:
        assert "invalid decision action" in str(exc)
    else:
        raise AssertionError("invalid action must be rejected")


def test_engine_maps_priority_to_decision():
    assessments = (
        RiskAssessment(
            target="critical.py",
            risk="high",
            priority="critical",
        ),
        RiskAssessment(
            target="high.py",
            risk="medium",
            priority="high",
        ),
        RiskAssessment(
            target="medium.py",
            risk="low",
            priority="medium",
        ),
        RiskAssessment(
            target="low.py",
            risk="minimal",
            priority="low",
        ),
    )

    result = ExecutionDecisionEngine().decide(assessments)

    assert [item.action for item in result] == [
        "auto_apply",
        "require_review",
        "simulate_first",
        "ignore",
    ]


def test_engine_preserves_assessment_data():
    assessment = RiskAssessment(
        target="x.py",
        risk="high",
        priority="critical",
        reason="critical dependency",
    )

    result = ExecutionDecisionEngine().decide((assessment,))

    assert result[0].target == "x.py"
    assert result[0].priority == "critical"
    assert result[0].risk == "high"
    assert result[0].reason == "critical dependency"


def test_engine_rejects_invalid_input():
    try:
        ExecutionDecisionEngine().decide(({"target": "x.py"},))
    except TypeError as exc:
        assert "RiskAssessment" in str(exc)
    else:
        raise AssertionError("invalid assessment must be rejected")
