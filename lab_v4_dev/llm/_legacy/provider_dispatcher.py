"""
Provider Dispatcher
v5.9.13-dev
"""

from lab_v4_dev.config.provider_config import get_active_provider

def get_provider():
    """
    يعيد اسم المزود النشط.
    """
    return get_active_provider()


def dispatch():
    """
    يعيد المزود الذي سيستخدمه Gateway.
    """
    provider = get_provider()

    if provider == "groq":
        return "groq"

    return provider
