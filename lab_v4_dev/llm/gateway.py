"""
CyberLab LLM Gateway
P08 — Canonical Gateway Execution Boundary
"""

from lab_v4_dev.llm.provider_registry import (
    get_provider,
    is_provider_available,
)
from lab_v4_dev.config.provider_config import is_provider_enabled
from lab_v4_dev.dni.privacy_engine import PrivacyEngine
from lab_v4_dev.llm.model_router import route
from lab_v4_dev.config.provider_config import (
    get_active_provider,
    get_fallback_provider,
)
from lab_v4_dev.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMError,
)

CHAIN = ["openrouter", "gemini", "groq", "local", "dummy"]

privacy = PrivacyEngine()



def _normalize_error(exc, provider, model=None):
    """
    Convert provider exceptions into the canonical LLMError contract.
    """

    if isinstance(exc, TimeoutError):
        return LLMError(
            code="TIMEOUT",
            message=str(exc) or "Provider timeout",
            provider=provider,
            retryable=True,
            timeout=True,
        )

    return LLMError(
        code="PROVIDER_EXCEPTION",
        message=str(exc) or "Provider execution failed",
        provider=provider,
        retryable=False,
        timeout=False,
    )


def _provider_chain(active, fallback):
    providers = []

    if active in CHAIN:
        providers.append(active)

    if fallback in CHAIN and fallback not in providers:
        providers.append(fallback)

    for name in CHAIN:
        if name not in providers:
            providers.append(name)

    return providers


def _prepare_request(
    prompt,
    system=None,
    max_tokens=800,
    model=None,
    temperature=0.3,
    timeout_ms=None,
):
    inspection = privacy.inspect(prompt)

    sanitized = inspection.get("sanitized", prompt)
    sanitized = privacy.sanitize(sanitized)

    return LLMRequest(
        prompt=sanitized,
        system=system,
        max_tokens=max_tokens,
        model=model,
        temperature=temperature,
        timeout_ms=timeout_ms,
    )


def _response_to_dict(resp: LLMResponse) -> dict:
    """Normalize LLMResponse dataclass into a plain dict that callers expect.

    This adapter keeps the gateway's internal contract (LLMResponse) but
    exposes a stable dict interface to the rest of the codebase where many
    callers use dict-like access (result.get(...)).
    """
    metadata = dict(resp.metadata or {})
    out = {
        "status": resp.status,
        "text": resp.text or "",
        "provider_used": resp.provider,
        "provider": resp.provider,
        "model": resp.model,
        "tokens": int(resp.tokens or 0),
        "fallback_used": bool(getattr(resp, "fallback_used", False)),
        "metadata": metadata,
        "provider_chain": metadata.get("provider_chain", []),
        "error": None,
    }

    if getattr(resp, "error", None):
        err = resp.error
        out["error"] = {
            "code": getattr(err, "code", None),
            "message": getattr(err, "message", str(err)),
            "provider": getattr(err, "provider", None),
            "retryable": getattr(err, "retryable", False),
            "timeout": getattr(err, "timeout", False),
            "details": getattr(err, "details", None),
        }

    return out


def ask(
    prompt,
    system=None,
    max_tokens=800,
    model=None,
    temperature=0.3,
    routing_text=None,
    timeout_ms=None,
):
    """
    Canonical Gateway entry point.

    Responsibilities:
        1. Privacy preprocessing
        2. Provider selection
        3. Centralized fallback ordering
        4. Provider execution through LLMRequest
        5. Canonical LLMResponse return (adapted to dict for callers)

    Provider-specific implementation details must not escape here.
    """

    request = _prepare_request(
        prompt=prompt,
        system=system,
        max_tokens=max_tokens,
        model=model,
        temperature=temperature,
        timeout_ms=timeout_ms,
    )

    decision = route(routing_text or request.prompt)

    active = decision.provider or get_active_provider()
    fallback = get_fallback_provider()

    providers = _provider_chain(active, fallback)

    last_error = None

    for name in providers:

        if not is_provider_available(name):
            continue

        if name != "dummy" and not is_provider_enabled(name):
            continue

        provider = get_provider(name)

        if provider is None:
            continue

        try:
            result = provider.execute(request)

            if not isinstance(result, LLMResponse):
                last_error = LLMResponse.failure(
                    error={
                        "code": "INVALID_GATEWAY_RESPONSE",
                        "message": "Provider did not return LLMResponse",
                    }
                    if False else __import__(
                        "lab_v4_dev.llm.contracts",
                        fromlist=["LLMError"],
                    ).LLMError(
                        code="INVALID_GATEWAY_RESPONSE",
                        message="Provider did not return LLMResponse",
                        provider=name,
                    ),
                    provider=name,
                    model=request.model,
                )
                # continue to next provider
                continue

            result.metadata = dict(result.metadata or {})
            result.metadata["provider_chain"] = providers

            if not result.provider:
                result.provider = name

            if not result.model:
                result.model = request.model

            # P08-B7:
            # A provider failure must not terminate the centralized
            # fallback chain. Continue to the next provider.
            if not result.ok:
                last_error = result
                continue

            # Successful LLMResponse — convert to dict for callers
            return _response_to_dict(result)

        except (TimeoutError, Exception) as exc:
            last_error = LLMResponse.failure(
                _normalize_error(
                    exc,
                    provider=name,
                    model=request.model,
                ),
                provider=name,
                model=request.model,
            )

    if last_error is not None:
        last_error.metadata = dict(last_error.metadata or {})
        last_error.metadata["provider_chain"] = providers
        return _response_to_dict(last_error)

    return _response_to_dict(
        LLMResponse.failure(
            LLMError(
                code="NO_PROVIDER_AVAILABLE",
                message="No configured provider is available",
                provider="gateway",
                retryable=False,
            ),
            provider="gateway",
            model=request.model,
            metadata={
                "provider_chain": providers,
            },
        )
    )
