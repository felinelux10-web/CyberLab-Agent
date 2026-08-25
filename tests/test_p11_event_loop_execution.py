from lab_v4_dev.executor.contracts import ExecutionResult
from lab_v4_dev.loop.event_loop import EventLoop


class FakeState:
    mode = "normal"

    def can_execute(self):
        return True

    def can_edit_files(self):
        return True

    def record_success(self):
        pass

    def record_failure(self):
        pass


class FakeMemory:
    tasks = None
    lessons = None


def test_event_loop_executes_planned_shell_step(monkeypatch):
    calls = []

    def fake_execute(self, request):
        calls.append(request)
        return ExecutionResult(
            status="success",
            plan_id=request.plan_id,
            step_id=request.step_id,
            action=request.action,
            stdout="P011_INTEGRATION_OK",
        )

    monkeypatch.setattr(
        "lab_v4_dev.executor.executor.Executor.execute",
        fake_execute,
    )

    loop = EventLoop(
        FakeState(),
        None,
        memory=FakeMemory(),
    )

    loop.submit("شغّل echo P011_INTEGRATION_OK")
    result = loop.tick()

    assert result["status"] == "executed"
    assert len(calls) == 1
    assert calls[0].action == "run_command"
    assert calls[0].parameters["command"] == "echo P011_INTEGRATION_OK"
    assert result["results"][0]["status"] == "success"
    assert result["results"][0]["stdout"] == "P011_INTEGRATION_OK"
