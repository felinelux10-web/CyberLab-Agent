"""
Dynamic Provider Loader
H.8.6.x
"""

from lab_v4_dev.config.provider_config import get_active_provider
from lab_v4_dev.llm.provider_registry import get_provider


def load():
    provider_name = get_active_provider()

    provider = get_provider(provider_name)

    if provider is None:
        raise RuntimeError(
            f"Provider '{provider_name}' is registered but not implemented."
        )

    return provider
