"""Orchestrator handler ownership package.

The package is introduced incrementally. Unregistered intents remain on the
legacy route until their ownership audit and behavior-preserving migration are
completed. No catch-all handler is provided.
"""

from .dispatch import HANDLER_REGISTRY, dispatch, registered_intents

__all__ = ["HANDLER_REGISTRY", "dispatch", "registered_intents"]
