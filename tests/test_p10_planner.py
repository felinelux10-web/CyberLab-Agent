from lab_v4_dev.planner.contracts import Plan, PlanStep
from lab_v4_dev.planner.planner import Planner


def test_planner_returns_plan_contract():
    planner = Planner()

    plan = planner.plan(
        {"action": "read_file", "target": "example.py"},
        (
            PlanStep(
                step_id="step-1",
                action="read_file",
                parameters={"file": "example.py"},
            ),
        ),
        plan_id="plan-001",
    )

    assert isinstance(plan, Plan)
    assert plan.plan_id == "plan-001"
    assert plan.count == 1


def test_planner_from_actions_builds_declarative_plan():
    planner = Planner()

    plan = planner.from_actions(
        {"action": "write_file", "target": "example.py"},
        [
            {
                "step_id": "step-1",
                "action": "write_file",
                "parameters": {
                    "file": "example.py",
                    "content": "print('hello')",
                },
            }
        ],
    )

    assert isinstance(plan, Plan)
    assert plan.steps[0].action == "write_file"
    assert plan.steps[0].parameters["file"] == "example.py"


def test_planner_does_not_execute():
    planner = Planner()

    plan = planner.from_actions(
        {"action": "shell"},
        [
            {
                "step_id": "step-1",
                "action": "shell",
                "parameters": {"command": "echo hello"},
            }
        ],
    )

    assert isinstance(plan, Plan)
    assert not hasattr(plan, "result")
    assert not hasattr(plan, "execution_result")
    assert not hasattr(plan, "executor")


def test_planner_preserves_dependencies():
    planner = Planner()

    plan = planner.from_actions(
        {"action": "pipeline"},
        [
            {
                "step_id": "step-1",
                "action": "read_file",
            },
            {
                "step_id": "step-2",
                "action": "write_file",
                "depends_on": ["step-1"],
            },
        ],
    )

    assert plan.steps[1].depends_on == ("step-1",)


def test_planner_rejects_invalid_intent():
    planner = Planner()

    try:
        planner.plan(
            "invalid",
            (
                PlanStep(step_id="step-1", action="read_file"),
            ),
        )
    except TypeError as exc:
        assert "intent must be a dict" in str(exc)
    else:
        raise AssertionError("invalid intent must be rejected")

def test_knowledge_router_exposes_p10_planner():
    from lab_v4_dev.dni import knowledge_router

    assert hasattr(knowledge_router, "create_p10_plan")



def test_legacy_execution_plan_adapter():
    from lab_v4_dev.planner.legacy_adapter import LegacyExecutionPlanAdapter

    plan = LegacyExecutionPlanAdapter().convert(
        {"action": "change_file", "target": "target.py"},
        [
            {
                "step": 1,
                "file": "critical.py",
                "priority": "critical",
                "action": "modify",
                "reason": "critical dependency",
            },
            {
                "step": 2,
                "file": "review.py",
                "priority": "high",
                "action": "review",
                "reason": "indirect dependency",
            },
        ],
    )

    assert plan.count == 2
    assert plan.steps[0].step_id == "step-1"
    assert plan.steps[0].action == "modify"
    assert plan.steps[0].parameters["file"] == "critical.py"
    assert plan.steps[0].parameters["priority"] == "critical"
    assert plan.steps[1].action == "review"


def test_legacy_execution_plan_adapter_rejects_invalid_input():
    from lab_v4_dev.planner.legacy_adapter import LegacyExecutionPlanAdapter

    try:
        LegacyExecutionPlanAdapter().convert(
            {"action": "change"},
            [{"priority": "critical"}],
        )
    except ValueError as exc:
        assert "file" in str(exc)
    else:
        raise AssertionError("missing file must be rejected")


def test_knowledge_router_can_bridge_legacy_change_plan_to_p10():
    from lab_v4_dev.dni.knowledge_router import create_p10_plan_from_change

    plan = create_p10_plan_from_change(
        "lab_v4_dev/core/orchestrator.py",
        plan_id="p10-bridge-test",
    )

    assert plan.plan_id == "p10-bridge-test"
    assert plan.count == 2
    assert plan.steps[0].parameters["file"] == "lab_v4_dev/core/agent.py"
    assert plan.steps[0].action == "modify"
    assert plan.steps[1].parameters["file"] == "run.py"
    assert plan.steps[1].action == "review"
