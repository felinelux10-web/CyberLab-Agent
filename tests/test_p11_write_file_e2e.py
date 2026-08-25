from pathlib import Path

from lab_v4_dev.executor.executor import Executor
from lab_v4_dev.executor.plan_adapter import PlanExecutionAdapter
from lab_v4_dev.executor.contracts import ExecutionResult
from lab_v4_dev.planner.contracts import Plan, PlanStep


class State:
    mode = "execute"

    def can_execute(self):
        return True

    def can_edit_files(self):
        return True

    def record_success(self):
        pass

    def record_failure(self):
        pass


class Session:
    def record_file_modified(self):
        pass


def test_p011_write_file_end_to_end(tmp_path):
    target = tmp_path / "p011_e2e.txt"

    plan = Plan(
        plan_id="p011-write-e2e",
        intent={"action": "write_file"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="write_file",
                parameters={
                    "file": str(target),
                    "content": "P011_WRITE_E2E_OK\n",
                },
            ),
        ),
    )

    request = PlanExecutionAdapter().to_request(plan, plan.steps[0])

    assert request.action == "write_file"
    assert request.parameters["file_path"] == str(target)
    assert request.parameters["content"] == "P011_WRITE_E2E_OK\n"

    executor = Executor(State(), None, Session())
    result = executor.execute(request)

    assert isinstance(result, ExecutionResult)
    assert result.status == "success"
    assert result.plan_id == "p011-write-e2e"
    assert result.step_id == "step-1"
    assert result.action == "write_file"
    assert result.target == str(target)

    assert target.exists()
    assert target.read_text() == "P011_WRITE_E2E_OK\n"


def test_p011_write_file_rejects_missing_content(tmp_path):
    target = tmp_path / "p011_missing_content.txt"

    executor = Executor(State(), None, Session())

    result = executor.execute(
        __import__(
            "lab_v4_dev.executor.contracts",
            fromlist=["ExecutionRequest"],
        ).ExecutionRequest(
            plan_id="p011-write-invalid",
            step_id="step-1",
            action="write_file",
            parameters={"file_path": str(target)},
        )
    )

    assert result.status == "failed"
    assert result.error == "parameters.content must be a string"
    assert not target.exists()
