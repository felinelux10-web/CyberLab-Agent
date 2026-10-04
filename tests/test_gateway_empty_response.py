from lab_v4_dev.llm import gateway
from lab_v4_dev.llm.contracts import LLMResponse


def test_gateway_falls_back_after_empty_successful_provider_response(monkeypatch):
    calls = []

    class Provider:
        def __init__(self, name, response):
            self.name = name
            self.response = response

        def execute(self, _request):
            calls.append(self.name)
            return self.response

    providers = {
        "openrouter": Provider(
            "openrouter",
            LLMResponse.success("   ", provider="openrouter"),
        ),
        "gemini": Provider(
            "gemini",
            LLMResponse.success("grounded answer", provider="gemini"),
        ),
    }

    monkeypatch.setattr(
        gateway,
        "route",
        lambda _text: type("Decision", (), {"provider": "openrouter"})(),
    )
    monkeypatch.setattr(gateway, "get_active_provider", lambda: "openrouter")
    monkeypatch.setattr(gateway, "get_fallback_provider", lambda: "gemini")
    monkeypatch.setattr(
        gateway,
        "_provider_chain",
        lambda _active, _fallback: ["openrouter", "gemini"],
    )
    monkeypatch.setattr(gateway, "is_provider_available", lambda _name: True)
    monkeypatch.setattr(gateway, "is_provider_enabled", lambda _name: True)
    monkeypatch.setattr(gateway, "get_provider", lambda name: providers[name])

    result = gateway.ask("hello", routing_text="hello")

    assert calls == ["openrouter", "gemini"]
    assert result["status"] == "success"
    assert result["text"] == "grounded answer"
    assert result["provider_used"] == "gemini"
    assert result["fallback_used"] is True
