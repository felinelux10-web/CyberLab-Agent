"""
P08 — Groq Provider Adapter.

Network/client implementation remains in groq_client.py.
This module only adapts it to the canonical provider contract.
"""

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.llm.contracts import LLMRequest, LLMResponse, LLMError
from lab_v4_dev.llm.groq_client import ask as groq_ask


class GroqProvider(BaseProvider):

    @property
    def name(self) -> str:
        return "groq"

    def execute(self, request: LLMRequest) -> LLMResponse:
        try:
            result = groq_ask(
                prompt=request.prompt,
                system=request.system,
                max_tokens=request.max_tokens,
                model=request.model,
                temperature=request.temperature,
            )

            if not isinstance(result, dict):
                return LLMResponse.failure(
                    LLMError(
                        code="INVALID_PROVIDER_RESPONSE",
                        message="Groq client returned non-dict response",
                        provider=self.name,
                    ),
                    provider=self.name,
                    model=request.model,
                )

            if result.get("status") == "success":
                return LLMResponse.success(
                    text=result.get("text", ""),
                    provider=self.name,
                    model=result.get("model") or request.model,
                    tokens=result.get("tokens", 0),
                )

            return LLMResponse.failure(
                LLMError(
                    code="PROVIDER_ERROR",
                    message=result.get("message", "Groq request failed"),
                    provider=self.name,
                    retryable=True,
                ),
                provider=self.name,
                model=result.get("model") or request.model,
            )

        except TimeoutError as exc:
            return LLMResponse.failure(
                LLMError(
                    code="TIMEOUT",
                    message=str(exc) or "Groq timeout",
                    provider=self.name,
                    retryable=True,
                    timeout=True,
                ),
                provider=self.name,
                model=request.model,
            )

        except Exception as exc:
            return LLMResponse.failure(
                LLMError(
                    code="PROVIDER_EXCEPTION",
                    message=str(exc),
                    provider=self.name,
                ),
                provider=self.name,
                model=request.model,
            )


provider = GroqProvider()
