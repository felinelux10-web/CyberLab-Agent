import inspect

from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.core.orchestrator_handlers.planning import handle_plan_change
from lab_v4_dev.core.orchestrator_handlers import dispatch


def test_plan_change_handler_uses_p10_plan_factory():
    # Ownership moved from Orchestrator._route into the registered planning handler.
    handler_source = inspect.getsource(handle_plan_change)
    dispatch_source = inspect.getsource(dispatch)

    assert "create_p10_plan_from_change" in handler_source
    assert "Intent.PLAN_CHANGE" in dispatch_source


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
