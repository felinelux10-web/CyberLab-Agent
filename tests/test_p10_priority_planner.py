from lab_v4_dev.planner.decision_contracts import (
    ImpactItem,
    PriorityAssessment,
)
from lab_v4_dev.planner.priority_planner import PriorityPlanner


def test_direct_impact_becomes_critical():
    items = (
        ImpactItem(
            file_path="lab_v4_dev/core/a.py",
            level="direct",
            reason="direct dependency",
        ),
    )

    result = PriorityPlanner().rank(items)

    assert result == (
        PriorityAssessment(
            target="lab_v4_dev/core/a.py",
            priority="critical",
            reason="direct dependency",
        ),
    )


def test_priority_mapping_is_complete():
    items = (
        ImpactItem("direct.py", "direct"),
        ImpactItem("indirect.py", "indirect"),
        ImpactItem("possible.py", "possible"),
        ImpactItem("unknown.py", "unknown"),
    )

    result = PriorityPlanner().rank(items)

    assert [item.priority for item in result] == [
        "critical",
        "high",
        "medium",
        "low",
    ]


def test_results_are_sorted_by_priority():
    items = (
        ImpactItem("low.py", "unknown"),
        ImpactItem("critical.py", "direct"),
        ImpactItem("medium.py", "possible"),
        ImpactItem("high.py", "indirect"),
    )

    result = PriorityPlanner().rank(items)

    assert [item.target for item in result] == [
        "critical.py",
        "high.py",
        "medium.py",
        "low.py",
    ]


def test_empty_input_returns_empty_tuple():
    assert PriorityPlanner().rank(()) == ()


def test_invalid_input_type_is_rejected():
    try:
        PriorityPlanner().rank("not-a-list")
    except TypeError as exc:
        assert "items must be" in str(exc)
    else:
        raise AssertionError("invalid input must be rejected")


def test_invalid_item_type_is_rejected():
    try:
        PriorityPlanner().rank(({"file_path": "x.py"},))
    except TypeError as exc:
        assert "ImpactItem" in str(exc)
    else:
        raise AssertionError("invalid item must be rejected")
