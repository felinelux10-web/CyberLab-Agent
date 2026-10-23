from lab_v4_dev.executor.contracts import ExecutionRequest
from lab_v4_dev.executor.executor import Executor
from lab_v4_dev.executor.plan_adapter import PlanExecutionAdapter
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


def executor():
    return Executor(State(), None, Session())


def request(**metadata):
    return ExecutionRequest(
        plan_id="stage5-plan",
        step_id="stage5-step",
        action="run_command",
        parameters={"command": "printf STAGE5_OK"},
        metadata=metadata,
    )


def test_dangerous_risk_requires_explicit_approval_before_execution():
    result = executor().execute(request(risk_level="dangerous"))

    assert result.status == "blocked"
    assert "explicit approval" in result.error


def test_approved_dangerous_risk_can_reach_execution():
    result = executor().execute(
        request(
            risk_level="dangerous",
            approval={"approved": True, "source": "user"},
        )
    )

    assert result.status == "success"
    assert result.stdout == "STAGE5_OK"


def test_safe_write_risk_requires_the_safe_write_policy_marker():
    result = executor().execute(request(risk_level="safe_write"))

    assert result.status == "blocked"
    assert "safe_write policy marker" in result.error


def test_safe_write_marker_allows_execution_boundary():
    result = executor().execute(
        request(risk_level="safe_write", write_policy="safe_write")
    )

    assert result.status == "success"
    assert result.stdout == "STAGE5_OK"


def test_plan_adapter_attaches_risk_metadata():
    plan = Plan(
        plan_id="dangerous-plan",
        intent={"intent": "clean"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="run_command",
                parameters={"command": "printf BLOCKED"},
            ),
        ),
    )

    request_ = PlanExecutionAdapter().to_request(plan, plan.steps[0])

    assert request_.metadata["risk_level"] == "dangerous"
    assert "approval" not in request_.metadata
    assert executor().execute(request_).status == "blocked"


def test_write_plan_gets_safe_write_marker_even_without_intent_label():
    plan = Plan(
        plan_id="write-plan",
        intent={"action": "write_file"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="write_file",
                parameters={"file": "stage5.txt", "content": "safe"},
            ),
        ),
    )

    request_ = PlanExecutionAdapter().to_request(plan, plan.steps[0])

    assert request_.metadata["risk_level"] == "safe_write"
    assert request_.metadata["write_policy"] == "safe_write"
