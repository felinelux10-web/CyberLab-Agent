from lab_v4_dev.dni.knowledge_router import (
    create_p10_plan_from_change,
)
from lab_v4_dev.planner.contracts import Plan


def test_p10_factory_returns_plan():
    result = create_p10_plan_from_change("example.py")

    assert isinstance(result, Plan)
    assert result.steps


def test_p10_factory_plan_is_declarative():
    result = create_p10_plan_from_change("example.py")

    assert isinstance(result, Plan)
    assert not hasattr(result, "execute")
    assert not hasattr(result, "rollback")
