import inspect

from lab_v4_dev.dni import knowledge_router


def test_knowledge_router_exposes_p10_plan_factory():
    assert hasattr(knowledge_router, "create_p10_plan_from_change")


def test_p10_factory_returns_declarative_plan():
    source = inspect.getsource(
        knowledge_router.create_p10_plan_from_change
    )

    assert "Planner" in source or "create_p10_plan" in source
    assert "LegacyExecutionPlanAdapter" in source


def test_knowledge_router_does_not_execute():
    source = inspect.getsource(knowledge_router)

    forbidden = (
        ".execute(",
        "run_command(",
        "write_file(",
        "rollback(",
    )

    for call in forbidden:
        assert call not in source
