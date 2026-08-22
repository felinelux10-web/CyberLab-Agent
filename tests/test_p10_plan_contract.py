from lab_v4_dev.planner.contracts import (
    PLAN_SCHEMA_VERSION,
    Plan,
    PlanStep,
)


def test_plan_step_is_declarative():
    step = PlanStep(
        step_id="step-1",
        action="read_file",
        parameters={"file": "example.py"},
        description="Read project file",
    )

    assert step.to_dict() == {
        "step_id": "step-1",
        "action": "read_file",
        "parameters": {"file": "example.py"},
        "depends_on": [],
        "description": "Read project file",
    }


def test_plan_is_serializable():
    plan = Plan(
        plan_id="plan-001",
        intent={"action": "read_file", "target": "example.py"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="read_file",
                parameters={"file": "example.py"},
            ),
        ),
    )

    data = plan.to_dict()

    assert data["plan_id"] == "plan-001"
    assert data["schema_version"] == PLAN_SCHEMA_VERSION
    assert data["steps"][0]["action"] == "read_file"


def test_plan_round_trip():
    original = Plan(
        plan_id="plan-002",
        intent={"action": "write_file", "target": "x.py"},
        steps=(
            PlanStep(
                step_id="step-1",
                action="write_file",
                parameters={"file": "x.py", "content": "print(1)"},
            ),
            PlanStep(
                step_id="step-2",
                action="shell",
                parameters={"command": "python3 x.py"},
                depends_on=("step-1",),
            ),
        ),
    )

    restored = Plan.from_dict(original.to_dict())

    assert restored == original


def test_duplicate_step_ids_are_rejected():
    try:
        Plan(
            intent={},
            steps=(
                PlanStep(step_id="step-1", action="read_file"),
                PlanStep(step_id="step-1", action="shell"),
            ),
        )
    except ValueError as exc:
        assert "duplicate step_id" in str(exc)
    else:
        raise AssertionError("duplicate step IDs must be rejected")


def test_unknown_dependencies_are_deferred_to_validator():
    plan = Plan(
        intent={},
        steps=(
            PlanStep(
                step_id="step-1",
                action="shell",
                depends_on=("missing",),
            ),
        ),
    )

    assert plan.steps[0].depends_on == ("missing",)
