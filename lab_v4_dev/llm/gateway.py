"""
CyberLab LLM Gateway
v5.9.13-dev
"""

from lab_v4_dev.llm.provider_registry import get_provider
from lab_v4_dev.dni.privacy_engine import PrivacyEngine
from lab_v4_dev.llm.model_router import route
from lab_v4_dev.config.provider_config import (
    get_active_provider,
    get_fallback_provider,
)

CHAIN = ["openrouter", "gemini", "groq", "local", "dummy"]


privacy = PrivacyEngine()


def ask(
    prompt,
    system=None,
    max_tokens=800,
    model=None,
    temperature=0.3,
    routing_text=None,
):
    inspection = privacy.inspect(prompt)
    prompt = privacy.sanitize(inspection.get("sanitized", prompt))

    decision = route(routing_text or prompt)

    active = decision.provider or get_active_provider()
    fallback = get_fallback_provider()

    providers = []

    if active in CHAIN:
        providers.append(active)

    if fallback in CHAIN and fallback not in providers:
        providers.append(fallback)

    for p in CHAIN:
        if p not in providers:
            providers.append(p)

    last_error = None

    for name in providers:

        provider = get_provider(name)

        if provider is None:
            continue

        try:

            result = provider.ask(
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                model=model,
                temperature=temperature,
            )

            if result.get("status") == "success":

                result = dict(result)

                result["provider_used"] = name

                result["provider_chain"] = providers

                if not result.get("model"):
                    result["model"] = model

                if not result.get("provider"):
                    result["provider"] = name

                return result

            last_error = result

        except Exception as e:

            last_error = {
                "status": "error",
                "provider": name,
                "message": str(e),
            }

    return {
        "status": "error",
        "provider": "gateway",
        "provider_chain": providers,
        "provider_used": None,
        "message": last_error,
        "text": "",
        "error": last_error,
    }
