"""
P08 — OpenRouter Provider Adapter.
"""

import requests

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.llm.contracts import LLMRequest, LLMResponse, LLMError
from lab_v4_dev.config.provider_config import get_provider_config


class OpenRouterProvider(BaseProvider):

    @property
    def name(self) -> str:
        return "openrouter"

    def execute(self, request: LLMRequest) -> LLMResponse:
        cfg = get_provider_config("openrouter")

        api_key = cfg.get("api_key", "")
        model_name = request.model or cfg.get("model")
        url = cfg.get("base_url")

        messages = []

        if request.system:
            messages.append({
                "role": "system",
                "content": request.system,
            })

        messages.append({
            "role": "user",
            "content": request.prompt,
        })

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        try:
            r = requests.post(
                url,
                headers=headers,
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

            text = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)

            return LLMResponse.success(
                text=text,
                provider=self.name,
                model=model_name,
                tokens=tokens,
            )

        except requests.Timeout as exc:
            return LLMResponse.failure(
                LLMError(
                    code="TIMEOUT",
                    message=str(exc) or "OpenRouter timeout",
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


provider = OpenRouterProvider()
