"""Immutable request-scoped context passed to domain handlers."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HandlerContext:
    intent: Any
    target: str | None = None
    raw: str | None = None
    route_decision: Any = None
    session_selector: dict = field(default_factory=dict)
    response_attributes: dict = field(default_factory=dict)
    conversation_history: list = field(default_factory=list)
    context_transition: str | None = None
    authorized_provider: Any = None


@dataclass
class HandlerFacade:
    """Narrow compatibility facade; intentionally exposes no Agent object."""

    context: Any
    services: Any
    request: HandlerContext
    pipeline: Any = None

    def _get_pipeline(self):
        if self.pipeline is None:
            from lab_v4_dev.executor.safe_pipeline import SafePipeline
            self.pipeline = SafePipeline(self.services.db)
        return self.pipeline


def build_handler_facade(orchestrator, request: HandlerContext):
    from .services import build_handler_services

    return HandlerFacade(
        context=getattr(orchestrator, "context", None),
        services=build_handler_services(orchestrator),
        request=request,
        pipeline=getattr(orchestrator, "pipeline", None),
    )


__all__ = ["HandlerContext", "HandlerFacade", "build_handler_facade"]
