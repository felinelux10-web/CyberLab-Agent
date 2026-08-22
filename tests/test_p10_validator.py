from lab_v4_dev.planner.contracts import Plan, PlanStep
from lab_v4_dev.planner.validator import validate_plan


def test_validator_accepts_valid_plan():
    plan = Plan(
        intent={"action": "read_file"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="read_file",
                parameters={"file": "example.py"},
            ),
        ),
    )

    result = validate_plan(plan)

    assert result["ok"] is True
    assert result["steps_count"] == 1
    assert result["errors"] == []


def test_validator_rejects_non_plan():
    result = validate_plan({"steps": []})

    assert result["ok"] is False
    assert "Plan instance" in result["errors"][0]


def test_validator_does_not_perform_execution_security_checks():
    plan = Plan(
        intent={"action": "shell"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="shell",
                parameters={"command": "rm -rf /tmp/example"},
            ),
        ),
    )

    result = validate_plan(plan)

    assert result["ok"] is True


def test_validator_accepts_forward_dependency():
    plan = Plan(
        intent={"action": "pipeline"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="write_file",
                depends_on=("step-2",),
            ),
            PlanStep(
                step_id="step-2",
                action="read_file",
            ),
        ),
    )

    result = validate_plan(plan)

    assert result["ok"] is True


def test_validator_rejects_invalid_dependency():
    plan = Plan(
        intent={"action": "pipeline"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="read_file",
                depends_on=("missing",),
            ),
        ),
    )

    result = validate_plan(plan)

    assert result["ok"] is False
    assert "unknown dependencies" in result["errors"][0]
