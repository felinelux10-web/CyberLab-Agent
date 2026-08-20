"""
P08 — Gemini Provider Adapter.
"""

import requests

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.llm.contracts import LLMRequest, LLMResponse, LLMError
from lab_v4_dev.config.provider_config import get_provider_config


class GeminiProvider(BaseProvider):

    @property
    def name(self) -> str:
        return "gemini"

    def execute(self, request: LLMRequest) -> LLMResponse:
        cfg = get_provider_config("gemini")

        api_key = cfg.get("api_key", "")
        model_name = request.model or cfg.get("model", "gemini-2.5-flash")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + model_name
            + ":generateContent?key="
            + api_key
        )

        text_prompt = (
            ((request.system + "\n\n") if request.system else "")
            + request.prompt
        )

        payload = {
            "contents": [{"parts": [{"text": text_prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        try:
            r = requests.post(
                url,
                json=payload,
                timeout=(
                    request.timeout_ms / 1000
                    if request.timeout_ms
                    else 30
                ),
            )

            data = r.json()

            if r.status_code != 200:
                return LLMResponse.failure(
                    LLMError(
                        code=f"HTTP_{r.status_code}",
                        message=str(data),
                        provider=self.name,
                        retryable=r.status_code >= 500,
                    ),
                    provider=self.name,
                    model=model_name,
                )

            text = data["candidates"][0]["content"]["parts"][0]["text"]

            return LLMResponse.success(
                text=text,
                provider=self.name,
                model=model_name,
            )

        except requests.Timeout as exc:
            return LLMResponse.failure(
                LLMError(
                    code="TIMEOUT",
                    message=str(exc) or "Gemini timeout",
                    provider=self.name,
                    retryable=True,
                    timeout=True,
                ),
                provider=self.name,
                model=model_name,
            )

        except Exception as exc:
            return LLMResponse.failure(
                LLMError(
                    code="PROVIDER_EXCEPTION",
                    message=str(exc),
                    provider=self.name,
                ),
                provider=self.name,
                model=model_name,
            )


provider = GeminiProvider()
