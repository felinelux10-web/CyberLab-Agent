import inspect

from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.core.orchestrator_handlers.planning import handle_plan_change
import lab_v4_dev.core.orchestrator_handlers.dispatch as dispatch_module
from lab_v4_dev.intent.intents import Intent


def test_plan_change_handler_uses_p10_plan_factory():
    # Verify both the implementation and the actual ownership registration.
    handler_source = inspect.getsource(handle_plan_change)

    assert "create_p10_plan_from_change" in handler_source
    assert dispatch_module.HANDLER_REGISTRY[Intent.PLAN_CHANGE] is handle_plan_change


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
