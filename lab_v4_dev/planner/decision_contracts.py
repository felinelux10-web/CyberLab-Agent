from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RISK_LEVELS = ("minimal", "low", "medium", "high")
PRIORITY_LEVELS = ("low", "medium", "high", "critical")
IMPACT_LEVELS = ("direct", "indirect", "possible", "unknown")


@dataclass(frozen=True)
class ImpactAssessment:
    target: str
    affected: tuple[str, ...] = ()
    level: str = "unknown"
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.target:
            raise ValueError("target must not be empty")

        if self.level not in IMPACT_LEVELS:
            raise ValueError(f"invalid impact level: {self.level}")

        if not isinstance(self.affected, tuple):
            raise TypeError("affected must be a tuple")

    @property
    def affected_count(self) -> int:
        return len(self.affected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "affected": list(self.affected),
            "affected_count": self.affected_count,
            "level": self.level,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ImpactItem:
    file_path: str
    level: str
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.file_path:
            raise ValueError("file_path must not be empty")

        if self.level not in IMPACT_LEVELS:
            raise ValueError(f"invalid impact level: {self.level}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "level": self.level,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PriorityAssessment:
    target: str
    priority: str
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.target:
            raise ValueError("target must not be empty")

        if self.priority not in PRIORITY_LEVELS:
            raise ValueError(f"invalid priority: {self.priority}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "priority": self.priority,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RiskAssessment:
    target: str
    risk: str
    priority: str
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.target:
            raise ValueError("target must not be empty")

        if self.risk not in RISK_LEVELS:
            raise ValueError(f"invalid risk level: {self.risk}")

        if self.priority not in PRIORITY_LEVELS:
            raise ValueError(f"invalid priority: {self.priority}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "risk": self.risk,
            "priority": self.priority,
            "reason": self.reason,
        }


__all__ = [
    "IMPACT_LEVELS",
    "PRIORITY_LEVELS",
    "RISK_LEVELS",
    "ImpactAssessment",
    "ImpactItem",
    "PriorityAssessment",
    "RiskAssessment",
]
