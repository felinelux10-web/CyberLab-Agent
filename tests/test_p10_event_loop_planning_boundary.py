import inspect

from lab_v4_dev.loop.event_loop import EventLoop


def test_event_loop_keeps_plan_contract_before_execution():
    source = inspect.getsource(EventLoop)

    # P10 planning must still exist.
    planning_pos = source.find("planner.from_actions")
    assert planning_pos >= 0

    # P11 execution must occur only after the plan is built.
    adapter_pos = source.find("plan_adapter.to_request")
    execution_pos = source.find("executor.execute")

    assert adapter_pos >= 0
    assert execution_pos >= 0
    assert planning_pos < adapter_pos < execution_pos


def test_event_loop_does_not_bypass_plan_adapter():
    source = inspect.getsource(EventLoop)

    assert "plan_adapter.to_request" in source

    # Direct legacy execution wrappers must not be used.
    assert "executor.run_command" not in source
    assert "executor.write_file" not in source
