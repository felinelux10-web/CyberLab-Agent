"""Orchestrator handler ownership package.

Keep the dispatch submodule addressable as a module. Exporting a function
under the same package attribute shadows that module and breaks normal
module-level patching/imports in callers and tests.
"""

from .dispatch import (
    HANDLER_REGISTRY,
    dispatch as dispatch_handler,
    registered_intents,
    route_request,
)

__all__ = [
    "HANDLER_REGISTRY",
    "dispatch_handler",
    "registered_intents",
    "route_request",
]
