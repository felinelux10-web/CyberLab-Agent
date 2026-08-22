import inspect

from lab_v4_dev.core.orchestrator import Orchestrator


def test_orchestrator_uses_p10_plan_factory():
    source = inspect.getsource(Orchestrator)

    assert "create_p10_plan_from_change" in source


def test_orchestrator_does_not_directly_consume_legacy_change_plan():
    source = inspect.getsource(Orchestrator)

    assert "ChangePlanner(" not in source
    assert "ExecutionPlan" not in source


def test_orchestrator_does_not_execute_plan_steps():
    source = inspect.getsource(Orchestrator)

    forbidden = (
        "executor.run_command",
        "executor.write_file",
        "executor.execute",
    )

    for call in forbidden:
        assert call not in source
