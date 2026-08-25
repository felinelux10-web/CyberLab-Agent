from lab_v4_dev.executor.executor import Executor
from lab_v4_dev.executor.contracts import ExecutionRequest


class DummyState:
    mode = "execute"

    def can_execute(self):
        return True

    def can_edit_files(self):
        return True

    def record_success(self):
        pass

    def record_failure(self):
        pass


class DummySession:
    def record_file_modified(self):
        pass


def make_executor():
    return Executor(
        DummyState(),
        None,
        DummySession(),
    )


def test_executor_requires_execution_request():
    executor = make_executor()

    try:
        executor.execute({"action": "run_command"})
    except TypeError:
        return

    raise AssertionError(
        "Executor accepted a non-ExecutionRequest"
    )


def test_executor_runs_command_and_returns_execution_result():
    executor = make_executor()

    request = ExecutionRequest(
        plan_id="p011-test",
        step_id="step-1",
        action="run_command",
        parameters={"command": "printf P011_OK"},
        metadata={"test": True},
    )

    result = executor.execute(request)

    assert result.status == "success"
    assert result.ok is True
    assert result.stdout == "P011_OK"
    assert result.plan_id == "p011-test"
    assert result.step_id == "step-1"
    assert result.action == "run_command"
    assert result.metadata["execution_schema"] == "p11.v1"
    assert result.metadata["test"] is True


def test_executor_rejects_unsupported_action():
    executor = make_executor()

    request = ExecutionRequest(
        plan_id="p011-test",
        step_id="step-2",
        action="unknown_action",
    )

    result = executor.execute(request)

    assert result.status == "unsupported"
    assert "unsupported execution action" in result.error


def test_executor_rejects_missing_command():
    executor = make_executor()

    request = ExecutionRequest(
        plan_id="p011-test",
        step_id="step-3",
        action="run_command",
        parameters={},
    )

    result = executor.execute(request)

    assert result.status == "failed"
    assert result.error == "missing parameters.command"


def test_execution_result_serialization():
    executor = make_executor()

    request = ExecutionRequest(
        plan_id="p011-test",
        step_id="step-4",
        action="run_command",
        parameters={"command": "printf SERIALIZED"},
    )

    result = executor.execute(request)
    data = result.to_dict()

    assert data["status"] == "success"
    assert data["plan_id"] == "p011-test"
    assert data["step_id"] == "step-4"
    assert data["stdout"] == "SERIALIZED"
    assert data["metadata"]["execution_schema"] == "p11.v1"


if __name__ == "__main__":
    executor = make_executor()

    result = executor.execute(
        ExecutionRequest(
            plan_id="p011-smoke",
            step_id="step-1",
            action="run_command",
            parameters={"command": "printf P011_OK"},
        )
    )

    assert result.status == "success"
    assert result.stdout == "P011_OK"

    print("=== P011 EXECUTOR SMOKE: PASS ===")


class BlockingState(DummyState):
    def can_execute(self):
        return False


class NoEditState(DummyState):
    def can_edit_files(self):
        return False


class RecordingState(DummyState):
    def __init__(self):
        self.successes = 0
        self.failures = 0

    def can_execute(self):
        return True

    def can_edit_files(self):
        return True

    def record_success(self):
        self.successes += 1

    def record_failure(self):
        self.failures += 1


def test_executor_blocks_when_state_disallows_execution():
    executor = Executor(BlockingState(), None, DummySession())

    result = executor.execute(
        ExecutionRequest(
            plan_id="p011-safety",
            step_id="blocked-1",
            action="run_command",
            parameters={"command": "printf SHOULD_NOT_RUN"},
        )
    )

    assert result.status == "blocked"
    assert "mode" in result.error


def test_executor_blocks_when_shell_command_limit_is_reached():
    executor = make_executor()
    from lab_v4_dev.core.config import HARD_LIMITS

    executor.commands_run = HARD_LIMITS["max_shell_commands_per_task"]

    result = executor.execute(
        ExecutionRequest(
            plan_id="p011-safety",
            step_id="limit-1",
            action="run_command",
            parameters={"command": "printf SHOULD_NOT_RUN"},
        )
    )

    assert result.status == "blocked"
    assert "limit" in result.error


def test_executor_normalizes_shell_failure_and_records_failure():
    state = RecordingState()
    executor = Executor(state, None, DummySession())

    result = executor.execute(
        ExecutionRequest(
            plan_id="p011-safety",
            step_id="failure-1",
            action="run_command",
            parameters={"command": "sh -c 'exit 7'"},
        )
    )

    assert result.status == "failed"
    assert result.exit_code == 7
    assert state.failures == 1


def test_executor_blocks_file_write_when_editing_is_disallowed():
    executor = Executor(NoEditState(), None, DummySession())

    result = executor.execute(
        ExecutionRequest(
            plan_id="p011-safety",
            step_id="write-blocked-1",
            action="write_file",
            parameters={
                "file_path": "_work/p011_should_not_exist.txt",
                "content": "SHOULD_NOT_BE_WRITTEN",
            },
        )
    )

    assert result.status == "blocked"
    assert "mode" in result.error


def test_executor_blocks_dangerous_shell_command():
    executor = make_executor()

    result = executor.execute(
        ExecutionRequest(
            plan_id="p011-safety",
            step_id="danger-1",
            action="run_command",
            parameters={"command": "rm -rf /"},
        )
    )

    assert result.status == "blocked"
    assert result.exit_code == -1
    assert "DNI-9 Security" in result.stderr


def test_executor_normalizes_timeout_and_records_failure(monkeypatch):
    state = RecordingState()
    executor = Executor(state, None, DummySession())

    def fake_timeout(command):
        return {
            "status": "timeout",
            "stdout": "",
            "stderr": "timeout",
            "code": -1,
        }

    monkeypatch.setattr(
        "lab_v4_dev.executor.executor.run_shell",
        fake_timeout,
    )

    result = executor.execute(
        ExecutionRequest(
            plan_id="p011-safety",
            step_id="timeout-1",
            action="run_command",
            parameters={"command": "sleep 999"},
        )
    )

    assert result.status == "timeout"
    assert result.exit_code == -1
    assert state.failures == 1
