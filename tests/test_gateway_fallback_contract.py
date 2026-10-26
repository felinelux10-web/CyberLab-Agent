from types import SimpleNamespace

import lab_v4_dev.llm.gateway as gateway
from lab_v4_dev.llm.contracts import LLMError, LLMResponse


class _Provider:
    def __init__(self, response):
        self.response = response

    def execute(self, _request):
        return self.response


def test_dummy_fallback_does_not_overwrite_the_real_provider_error(monkeypatch):
    monkeypatch.setattr(
        gateway,
        "route",
        lambda _text: SimpleNamespace(provider="openrouter"),
    )
    monkeypatch.setattr(gateway, "get_fallback_provider", lambda: "local")
    monkeypatch.setattr(
        gateway,
        "is_provider_available",
        lambda name: name in {"openrouter", "dummy"},
    )
    monkeypatch.setattr(
        gateway,
        "is_provider_enabled",
        lambda name: name == "openrouter",
    )
    monkeypatch.setattr(
        gateway,
        "get_provider",
        lambda name: (
            _Provider(LLMResponse.failure(
                LLMError(
                    code="TIMEOUT",
                    message="provider timed out",
                    provider="openrouter",
                    retryable=True,
                    timeout=True,
                ),
                provider="openrouter",
            ))
            if name == "openrouter"
            else _Provider(LLMResponse.fallback("dummy echo", provider="dummy"))
        ),
    )

    result = gateway.ask("ordinary conversational question")

    assert result["status"] == "error"
    assert result["provider_used"] == "openrouter"
    assert result["error"]["code"] == "TIMEOUT"
    assert result["text"] != "dummy echo"
    assert any(
        item["code"] == "FALLBACK_NOT_ACCEPTED"
        for item in result["metadata"]["provider_errors"]
    )
