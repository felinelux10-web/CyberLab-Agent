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

ROUTES = frozenset({
    "L-SOCIAL",
    "L-LIVE",
    "L-SESSION",
    "L-FACT",
    "L-EXEC",
    "P-TOOL",
    "CLARIFY",
    "DENY",
})

SESSION_SCOPES = frozenset({
    "none",
    "live_current",
    "saved_id",
    "saved_number",
    "previous_saved",
})

OUTPUT_KINDS = frozenset({
    "none",
    "brief",
    "summary",
    "report",
    "topic_summary",
    "transcript",
    "list",
    "continue_topic",
    "capability",
})

EVIDENCE_SCOPES = frozenset({
    "none",
    "live_exchanges",
    "saved_session",
    "project_state",
    "work_state",
})


@dataclass(frozen=True)
class SessionRef:
    """Explicit identity of a selected saved session."""

    session_id: str
    number: int | None = None

    def __post_init__(self) -> None:
        if not str(self.session_id).strip():
            raise ValueError("session_id must be non-empty")
        if self.number is not None and (
            isinstance(self.number, bool) or int(self.number) < 1
        ):
            raise ValueError("session number must be a positive integer")


@dataclass(frozen=True)
class ContextLock:
    """Output/session ownership retained across compatible follow-up turns."""

    active: bool = False
    session_id: str | None = None
    topic: str | None = None
    output_kind: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.output_kind is not None and self.output_kind not in OUTPUT_KINDS:
            raise ValueError(f"invalid locked output_kind: {self.output_kind}")
        if self.active and not any((
            self.session_id,
            self.topic,
            self.output_kind,
        )):
            raise ValueError("an active context lock requires an owner or output")


@dataclass(frozen=True)
class RouteDecision:
    """Frozen, authoritative routing/output/ownership decision.

    ConversationManager is the sole runtime issuer. Downstream layers consume
    this value; SemanticRequest remains an interpretation input, not a route.
    Diagnostic metadata must never be used to override these fields.
    """

    route: str
    session_scope: str = "none"
    session_ref: SessionRef | None = None
    output_kind: str = "none"
    topic_filter: str | None = None
    context_lock: ContextLock = field(default_factory=ContextLock)
    evidence_scope: str = "none"
    provider_allowed: bool = False
    intent: Any = None
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.route not in ROUTES:
            raise ValueError(f"invalid route: {self.route}")
        if self.session_scope not in SESSION_SCOPES:
            raise ValueError(f"invalid session_scope: {self.session_scope}")
        if self.output_kind not in OUTPUT_KINDS:
            raise ValueError(f"invalid output_kind: {self.output_kind}")
        if self.evidence_scope not in EVIDENCE_SCOPES:
            raise ValueError(f"invalid evidence_scope: {self.evidence_scope}")
        if not isinstance(self.provider_allowed, bool):
            raise TypeError("provider_allowed must be bool")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.session_scope in {"saved_id", "saved_number", "previous_saved"}:
            if self.session_ref is None:
                raise ValueError("saved session scope requires session_ref")
        elif self.session_ref is not None:
            raise ValueError("session_ref is only valid for a saved session scope")
        if self.session_scope == "saved_id" and self.session_ref and self.session_ref.number is not None:
            raise ValueError("saved_id scope must not carry a session number")
        if self.session_scope == "saved_number" and self.session_ref and self.session_ref.number is None:
            raise ValueError("saved_number scope requires a session number")
        if self.evidence_scope == "saved_session" and self.session_ref is None:
            raise ValueError("saved_session evidence requires an explicit session_ref")
        if self.output_kind in {"summary", "brief", "report", "topic_summary", "transcript"}:
            if self.evidence_scope == "none":
                raise ValueError("dialogue output requires an explicit evidence_scope")


@dataclass(frozen=True)
class PreparedExecutionRequest:
    """Resolved execution handoff from orchestration to the execution path.

    Carries already-resolved execution inputs. Raw conversation text and
    planning actions are intentionally excluded so downstream execution
    cannot re-parse input or take ownership of planning.
    """

    intent: Any
    target: Any = None
    context: Context = field(default_factory=Context)
    request_id: str | None = None
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
    "RouteDecision",
    "SessionRef",
    "ContextLock",
    "ROUTES",
    "SESSION_SCOPES",
    "OUTPUT_KINDS",
    "EVIDENCE_SCOPES",
    "PreparedExecutionRequest",
    "AuditEvent",
]
