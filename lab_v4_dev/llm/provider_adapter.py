"""
P08 — Legacy Provider Adapter.

Keeps existing provider implementations intact while exposing the
canonical BaseProvider / LLMRequest / LLMResponse contract.
"""

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMError,
)


class LegacyProviderAdapter(BaseProvider):

    def __init__(self, provider_name, legacy_provider):
        self._name = provider_name
        self._provider = legacy_provider

    @property
    def name(self):
        return self._name

    def execute(self, request: LLMRequest) -> LLMResponse:
        try:
            result = self._provider.ask(
                prompt=request.prompt,
                system=request.system,
                max_tokens=request.max_tokens,
                model=request.model,
                temperature=request.temperature,
            )

            if isinstance(result, LLMResponse):
                return result

            if not isinstance(result, dict):
                return LLMResponse.failure(
                    LLMError(
                        code="INVALID_PROVIDER_RESPONSE",
                        message="Provider returned a non-dictionary response",
                        provider=self._name,
                        retryable=False,
                        details=repr(result),
                    ),
                    provider=self._name,
                )

            status = result.get("status")

            if status == "success":
                return LLMResponse.success(
                    text=result.get("text", result.get("message", "")),
                    provider=result.get("provider") or self._name,
                    model=result.get("model") or request.model,
                    tokens=result.get("tokens", 0),
                    metadata={
                        "legacy_response": result,
                    },
                )

            if status == "fallback":
                return LLMResponse.fallback(
                    text=result.get("text", result.get("message", "")),
                    provider=result.get("provider") or self._name,
                    model=result.get("model") or request.model,
                    metadata={
                        "legacy_response": result,
                    },
                )

            error = LLMError(
                code=result.get("code", "PROVIDER_ERROR"),
                message=str(
                    result.get("message")
                    or result.get("error")
                    or result.get("text")
                    or "Provider request failed"
                ),
                provider=self._name,
                retryable=bool(result.get("retryable", False)),
                timeout=bool(result.get("timeout", False)),
                details=result,
            )

            return LLMResponse.failure(
                error,
                provider=self._name,
                model=result.get("model") or request.model,
                metadata={
                    "legacy_response": result,
                },
            )

        except TimeoutError as exc:
            return LLMResponse.failure(
                LLMError(
                    code="TIMEOUT",
                    message=str(exc) or "Provider timeout",
                    provider=self._name,
                    retryable=True,
                    timeout=True,
                ),
                provider=self._name,
                model=request.model,
            )

        except Exception as exc:
            return LLMResponse.failure(
                LLMError(
                    code="PROVIDER_EXCEPTION",
                    message=str(exc),
                    provider=self._name,
                    retryable=False,
                ),
                provider=self._name,
                model=request.model,
            )
