import pytest

from lab_v4_dev.llm.contracts import LLMRequest
from lab_v4_dev.llm.openrouter_provider import OpenRouterProvider
import lab_v4_dev.llm.openrouter_provider as provider_module


@pytest.mark.parametrize(
    ("model", "token_key", "other_token_key", "has_temperature"),
    [
        ("openai/gpt-5-mini", "max_completion_tokens", "max_tokens", False),
        ("google/gemini-3-flash-preview", "max_tokens", "max_completion_tokens", True),
    ],
)
def test_openrouter_uses_model_family_token_contract(
    monkeypatch, model, token_key, other_token_key, has_temperature
):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 2},
            }

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        provider_module,
        "get_provider_config",
        lambda _name: {
            "api_key": "test-key",
            "model": model,
            "base_url": "https://proxy.invalid/v1/chat/completions",
        },
    )
    monkeypatch.setattr(provider_module.requests, "post", fake_post)

    response = OpenRouterProvider().execute(
        LLMRequest(
            prompt="hello",
            model=model,
            max_tokens=4000,
            temperature=0.7,
        )
    )

    payload = captured["payload"]
    assert response.ok
    assert response.text == "ok"
    assert payload[token_key] == 4000
    assert other_token_key not in payload
    assert ("temperature" in payload) is has_temperature
