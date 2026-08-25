from lab_v4_dev.planner.contracts import Plan, PlanStep
from lab_v4_dev.executor.plan_adapter import PlanExecutionAdapter
from lab_v4_dev.executor.contracts import ExecutionRequest


def test_shell_plan_step_maps_to_run_command():
    plan = Plan(
        plan_id="plan-1",
        intent={"action": "shell"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="shell",
                parameters={"command": "echo OK"},
            ),
        ),
    )

    request = PlanExecutionAdapter().to_request(plan, plan.steps[0])

    assert isinstance(request, ExecutionRequest)
    assert request.plan_id == "plan-1"
    assert request.step_id == "step-1"
    assert request.action == "run_command"
    assert request.parameters["command"] == "echo OK"


def test_write_file_plan_step_maps_file_to_file_path():
    plan = Plan(
        plan_id="plan-2",
        intent={"action": "write_file"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="write_file",
                parameters={
                    "file": "example.py",
                    "content": "print('OK')",
                },
            ),
        ),
    )

    request = PlanExecutionAdapter().to_request(plan, plan.steps[0])

    assert request.action == "write_file"
    assert request.parameters["file_path"] == "example.py"
    assert request.parameters["content"] == "print('OK')"
    assert "file" not in request.parameters


def test_adapter_rejects_invalid_inputs_and_unsupported_action():
    adapter = PlanExecutionAdapter()

    try:
        adapter.to_request({}, None)
        assert False, "expected TypeError for invalid plan"
    except TypeError:
        pass

    plan = Plan(
        plan_id="plan-invalid",
        intent={"action": "unknown"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="unknown",
                parameters={},
            ),
        ),
    )

    try:
        adapter.to_request(plan, plan.steps[0])
        assert False, "expected ValueError for unsupported action"
    except ValueError:
        pass


def test_edit_file_plan_step_maps_to_write_file():
    plan = Plan(
        plan_id="plan-3",
        intent={"action": "edit_file"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="edit_file",
                parameters={
                    "file": "example.py",
                    "content": "print('EDITED')",
                },
            ),
        ),
    )

    request = PlanExecutionAdapter().to_request(plan, plan.steps[0])

    assert request.action == "write_file"
    assert request.parameters["file_path"] == "example.py"
    assert request.parameters["content"] == "print('EDITED')"
    assert "file" not in request.parameters
