import inspect

from lab_v4_dev.loop.event_loop import EventLoop


def test_event_loop_must_not_execute_during_p10_planning():
    source = inspect.getsource(EventLoop)

    assert "planner.from_actions" in source
    assert "executor.run_command" not in source
    assert "executor.write_file" not in source


def test_event_loop_keeps_planning_and_execution_as_separate_phases():
    source = inspect.getsource(EventLoop)

    planning_pos = source.find("planner.from_actions")
    assert planning_pos >= 0

    execution_calls = (
        "executor.run_command",
        "executor.write_file",
        "executor.execute",
    )

    for call in execution_calls:
        assert source.find(call) == -1
