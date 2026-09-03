"""
CyberLab Agent — P00 Foundation Contracts

Stable architectural boundaries.

P00 introduces typed internal contracts while preserving the existing
legacy dictionary runtime representation. No routing semantics are
changed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Dict


@dataclass(frozen=True)
class Request:
    """Canonical representation of incoming user input."""

    raw_text: str
    request_id: str | None = None
    source: str = "user"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_input(cls, value: Any) -> "Request":
        if isinstance(value, cls):
            return value

        if isinstance(value, Mapping):
            return cls(
                raw_text=str(
                    value.get(
                        "raw_text",
                        value.get("request", value.get("text", "")),
                    )
                ),
                request_id=value.get("request_id"),
                source=str(value.get("source", "user")),
                metadata=dict(value.get("metadata", {})),
            )

        return cls(raw_text=str(value))


@dataclass
class Context:
    """Operational context boundary."""

    subject: Any = None
    version: Any = None
    file: Any = None
    analysis: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_store(cls, store: Any) -> "Context":
        return cls(
            subject=getattr(store, "current_subject", None),
            version=getattr(store, "current_version", None),
            file=getattr(store, "current_file", None),
            analysis=getattr(store, "current_analysis", None),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "version": self.version,
            "file": self.file,
            "analysis": self.analysis,
            "metadata": dict(self.metadata),
        }


@dataclass
class Result:
    """Canonical internal execution result."""

    status: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legacy(cls, value: Any) -> "Result":
        if isinstance(value, cls):
            return value

        if isinstance(value, Mapping):
            data = dict(value)
            status = str(data.pop("status", "unknown"))
            return cls(status=status, data=data)

        return cls(status="success", data={"value": value})

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, **self.data}


@dataclass
class Response:
    """Public response boundary."""

    result: Result
    request_id: str | None = None

    @classmethod
    def from_legacy(
        cls,
        value: Any,
        request_id: str | None = None,
    ) -> "Response":
        return cls(
            result=Result.from_legacy(value),
            request_id=request_id,
        )

    def to_dict(self) -> dict[str, Any]:
        data = self.result.to_dict()

        if self.request_id is not None and "request_id" not in data:
            data["request_id"] = self.request_id

        return data


@dataclass(frozen=True)
class RoutingDecision:
    """Explicit boundary between interpretation and orchestration."""

    intent: Any = None
    target: Any = None
    route: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEvent:
    """Minimal contract for P014 audit events (compatible with EventRecord)."""
    timestamp: str
    event: str
    source: str
    context: Dict[str, Any]
    details: Dict[str, Any]


__all__ = [
    "Request",
    "Context",
    "Result",
    "Response",
    "RoutingDecision",
    "AuditEvent",
]
