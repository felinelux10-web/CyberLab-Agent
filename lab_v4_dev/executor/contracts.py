from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXECUTION_SCHEMA_VERSION = "p11.v1"


@dataclass(frozen=True)
class ExecutionRequest:
    """Validated handoff from P010 planning to P011 execution."""

    plan_id: str
    step_id: str
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("plan_id must not be empty")
        if not self.step_id:
            raise ValueError("step_id must not be empty")
        if not self.action:
            raise ValueError("action must not be empty")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be a dict")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dict")


@dataclass(frozen=True)
class ExecutionContext:
    """Execution identity/context; contains no planning decisions."""

    plan_id: str
    step_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("plan_id must not be empty")
        if not self.step_id:
            raise ValueError("step_id must not be empty")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dict")


@dataclass(frozen=True)
class ExecutionResult:
    """Canonical P011 result returned after an execution attempt."""

    status: str
    plan_id: str
    step_id: str
    action: str
    target: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status:
            raise ValueError("status must not be empty")
        if not self.plan_id:
            raise ValueError("plan_id must not be empty")
        if not self.step_id:
            raise ValueError("step_id must not be empty")
        if not self.action:
            raise ValueError("action must not be empty")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dict")

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan_id": self.plan_id,
            "step_id": self.step_id,
            "action": self.action,
            "target": self.target,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "error": self.error,
            "metadata": dict(self.metadata),
        }
