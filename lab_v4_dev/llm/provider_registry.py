"""
Provider Registry - small extension: explicit availability helper
"""
from lab_v4_dev.llm.provider_names import *

from lab_v4_dev.llm.groq_provider import provider as groq_provider
from lab_v4_dev.llm.dummy_provider import provider as dummy_provider
from lab_v4_dev.llm.gemini_provider import provider as gemini_provider
from lab_v4_dev.llm.openrouter_provider import provider as openrouter_provider
from lab_v4_dev.llm.provider_adapter import LegacyProviderAdapter

REGISTRY = {
    GROQ: LegacyProviderAdapter(GROQ, groq_provider),
    DUMMY: LegacyProviderAdapter(DUMMY, dummy_provider),
    GEMINI: LegacyProviderAdapter(GEMINI, gemini_provider),
    OPENROUTER: LegacyProviderAdapter(OPENROUTER, openrouter_provider),

    OPENAI: None,
    LOCAL: None,
}


def has_provider(name: str) -> bool:
    return name in REGISTRY


def get_provider(name: str):
    if name not in REGISTRY:
        raise KeyError(f"Unknown provider: {name}")
    return REGISTRY[name]


def is_provider_available(name: str) -> bool:
    """
    True if provider exists and is not None (i.e., actually implemented).
    """
    return name in REGISTRY and REGISTRY.get(name) is not None


def register(name: str, provider):
    REGISTRY[name] = provider


def unregister(name: str):
    if name in REGISTRY:
        del REGISTRY[name]


def list_providers():
    return sorted(REGISTRY.keys())
