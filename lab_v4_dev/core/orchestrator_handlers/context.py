"""Immutable request-scoped context passed to domain handlers."""

from dataclasses import dataclass, field
from typing import Any

from lab_v4_dev.core.contracts import FrozenList, freeze_contract_value


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

    def __post_init__(self):
        object.__setattr__(self, "session_selector", freeze_contract_value(self.session_selector or {}))
        object.__setattr__(self, "response_attributes", freeze_contract_value(self.response_attributes or {}))
        object.__setattr__(self, "conversation_history", freeze_contract_value(self.conversation_history or []))


@dataclass
class HandlerFacade:
    """Narrow compatibility facade; intentionally exposes no Agent object."""

    context: Any
    services: Any
    request: HandlerContext
    pipeline: Any = None

    def _get_pipeline(self):
        if self.pipeline is None:
            factory = self.services.pipeline_factory
            if callable(factory):
                self.pipeline = factory()
            else:
                from lab_v4_dev.executor.safe_pipeline import SafePipeline
                self.pipeline = SafePipeline(self.services.db)
        return self.pipeline


def build_handler_facade(orchestrator, request: HandlerContext):
    from .services import build_handler_services

    return HandlerFacade(
        context=getattr(orchestrator, "context", None),
        services=build_handler_services(orchestrator, intent=request.intent),
        request=request,
        pipeline=getattr(orchestrator, "pipeline", None),
    )


__all__ = ["HandlerContext", "HandlerFacade", "build_handler_facade"]
