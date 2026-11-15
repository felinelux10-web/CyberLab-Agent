"""Read-only provider classification derived from the canonical handler registry.

This module does not own intent routing. HANDLER_REGISTRY is the sole owner
map; these helpers only report whether an already-registered owner is the
provider-backed handler.
"""

from lab_v4_dev.config.provider_config import get_active_provider
from lab_v4_dev.core.orchestrator_handlers.dispatch import HANDLER_REGISTRY
from lab_v4_dev.core.orchestrator_handlers.provider_fallback import handle_provider_intent


def needs_llm(intent: str) -> bool:
    return HANDLER_REGISTRY.get(intent) is handle_provider_intent


def is_local(intent: str) -> bool:
    return intent in HANDLER_REGISTRY and not needs_llm(intent)


def route(intent: str) -> str:
    return get_active_provider() if needs_llm(intent) else "local"
