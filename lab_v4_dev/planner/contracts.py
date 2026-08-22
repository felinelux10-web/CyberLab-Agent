from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PLAN_SCHEMA_VERSION = "p10.v1"


@dataclass(frozen=True)
class PlanStep:
    """
    Declarative planning step.

    This object describes what an executor may later perform.
    It performs no execution and contains no execution state.
    """

    step_id: str
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("step_id must not be empty")

        if not self.action:
            raise ValueError("action must not be empty")

        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be a dict")

        if not isinstance(self.depends_on, tuple):
            raise TypeError("depends_on must be a tuple")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "parameters": dict(self.parameters),
            "depends_on": list(self.depends_on),
            "description": self.description,
        }


@dataclass(frozen=True)
class Plan:
    """
    Declarative execution plan.

    Plan construction is a planning concern only.
    This contract must not contain execution results, permissions,
    transactions, recovery state, or runtime handles.
    """

    intent: dict[str, Any]
    steps: tuple[PlanStep, ...]
    schema_version: str = PLAN_SCHEMA_VERSION
    plan_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.intent, dict):
            raise TypeError("intent must be a dict")

        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")

        if not self.steps:
            raise ValueError("plan must contain at least one step")

        seen: set[str] = set()

        for step in self.steps:
            if not isinstance(step, PlanStep):
                raise TypeError("steps must contain PlanStep objects")

            if step.step_id in seen:
                raise ValueError(f"duplicate step_id: {step.step_id}")

            seen.add(step.step_id)


    @property
    def count(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "schema_version": self.schema_version,
            "intent": dict(self.intent),
            "steps": [step.to_dict() for step in self.steps],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        if not isinstance(data, dict):
            raise TypeError("plan data must be a dict")

        raw_steps = data.get("steps", [])

        steps = tuple(
            PlanStep(
                step_id=item["step_id"],
                action=item["action"],
                parameters=dict(item.get("parameters", {})),
                depends_on=tuple(item.get("depends_on", [])),
                description=item.get("description", ""),
            )
            for item in raw_steps
        )

        return cls(
            plan_id=data.get("plan_id", ""),
            schema_version=data.get("schema_version", PLAN_SCHEMA_VERSION),
            intent=dict(data.get("intent", {})),
            steps=steps,
            metadata=dict(data.get("metadata", {})),
        )
