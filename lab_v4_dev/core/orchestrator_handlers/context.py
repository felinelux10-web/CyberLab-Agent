"""Immutable request-scoped context passed to domain handlers."""

from dataclasses import dataclass, field
from typing import Any

from lab_v4_dev.core.contracts import FrozenDict


class FrozenList(list):
    """List-compatible immutable container used by request contracts."""

    def __init__(self, values=()):
        list.__init__(self, (_freeze(value) for value in values))

    def _immutable(self, *_args, **_kwargs):
        raise TypeError("FrozenList does not support mutation")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable

    def __deepcopy__(self, memo):
        return self


def _freeze(value):
    if isinstance(value, FrozenDict) or isinstance(value, FrozenList):
        return value
    if isinstance(value, dict):
        return FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return FrozenList(value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


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
        object.__setattr__(self, "session_selector", _freeze(self.session_selector or {}))
        object.__setattr__(self, "response_attributes", _freeze(self.response_attributes or {}))
        object.__setattr__(self, "conversation_history", _freeze(self.conversation_history or []))


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
