"""Legacy adapter for provider calls requiring an injected authorization capability.

This module deliberately has no gateway import and cannot select a provider.
"""
from __future__ import annotations


def ask(prompt, *, authorized_ask=None, **kwargs):
    if not callable(authorized_ask):
        return {
            "status": "unavailable",
            "source": "provider_capability_missing",
            "message": "An authorized provider capability is required.",
        }
    result = authorized_ask(prompt, **kwargs)
    return result
