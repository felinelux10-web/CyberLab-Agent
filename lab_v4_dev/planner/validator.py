from __future__ import annotations

from lab_v4_dev.planner.contracts import Plan


def validate_plan(plan: Plan) -> dict:
    """
    Validate the structural planning contract only.

    This validator does NOT:
    - execute anything
    - check filesystem permissions
    - inspect frozen zones
    - approve/reject shell commands
    - perform risk decisions
    - create snapshots or recovery state

    Those concerns belong to downstream safety/execution layers.
    """

    errors: list[str] = []

    if not isinstance(plan, Plan):
        return {
            "ok": False,
            "errors": ["plan must be a Plan instance"],
        }

    if not plan.steps:
        errors.append("plan has no steps")

    seen: set[str] = set()

    for index, step in enumerate(plan.steps):
        if step.step_id in seen:
            errors.append(
                f"step {index} duplicate step_id: {step.step_id}"
            )

        seen.add(step.step_id)

        unknown_dependencies = set(step.depends_on) - seen - {
            future.step_id for future in plan.steps[index + 1:]
        }

        if unknown_dependencies:
            errors.append(
                f"step {index} unknown dependencies: "
                f"{sorted(unknown_dependencies)}"
            )

    if errors:
        return {
            "ok": False,
            "errors": errors,
            "steps_count": len(plan.steps),
        }

    return {
        "ok": True,
        "errors": [],
        "steps_count": len(plan.steps),
    }


__all__ = ["validate_plan"]
