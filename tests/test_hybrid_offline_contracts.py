import requests

import lab_v4_dev.llm.gateway as gateway
import lab_v4_dev.conversation.conversation_manager as manager_module
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.llm.contracts import LLMError, LLMRequest, LLMResponse
from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.llm.openrouter_provider import OpenRouterProvider
from lab_v4_dev.llm.provider_adapter import LegacyProviderAdapter
from lab_v4_dev.llm.provider_registry import get_provider, is_provider_available


class OfflineProvider:
    def __init__(self, name):
        self.name = name
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return LLMResponse.failure(
            LLMError(
                code="CONNECTION_ERROR",
                message="network unavailable",
                provider=self.name,
                retryable=True,
            ),
            provider=self.name,
        )


class DialogueOnlyOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, parsed, kwargs))
        return {"status": "success", "text": "unexpected execution response"}


def test_registry_exposes_canonical_execute_providers_without_legacy_adapter():
    for name in ("openrouter", "gemini", "groq", "dummy"):
        provider = get_provider(name)
        assert is_provider_available(name)
        assert isinstance(provider, BaseProvider)
        assert not isinstance(provider, LegacyProviderAdapter)
        assert callable(getattr(provider, "execute", None))


def test_dummy_is_not_part_of_the_normal_provider_chain():
    assert "dummy" not in gateway.CHAIN
    assert "dummy" not in gateway._provider_chain("openrouter", "local")


def test_gateway_preserves_connection_failure_and_never_uses_dummy(monkeypatch):
    providers = {
        name: OfflineProvider(name)
        for name in ("openrouter", "gemini", "groq")
    }
    monkeypatch.setattr(gateway, "route", lambda _text: type("Decision", (), {"provider": "openrouter"})())
    monkeypatch.setattr(gateway, "get_active_provider", lambda: "openrouter")
    monkeypatch.setattr(gateway, "get_fallback_provider", lambda: "local")
    monkeypatch.setattr(gateway, "is_provider_enabled", lambda name: name != "local")
    monkeypatch.setattr(
        gateway,
        "is_provider_available",
        lambda name: name in providers,
    )
    monkeypatch.setattr(gateway, "get_provider", lambda name: providers[name])

    result = gateway.ask("Explain a general concept", routing_text="general question")

    assert result["status"] == "error"
    assert result["error"]["code"] == "CONNECTION_ERROR"
    assert "dummy" not in result["provider_chain"]
    assert all(provider.calls == 1 for provider in providers.values())


def test_no_available_provider_returns_error_instead_of_dummy_fallback(monkeypatch):
    monkeypatch.setattr(gateway, "route", lambda _text: type("Decision", (), {"provider": "openrouter"})())
    monkeypatch.setattr(gateway, "get_active_provider", lambda: "openrouter")
    monkeypatch.setattr(gateway, "get_fallback_provider", lambda: "local")
    monkeypatch.setattr(gateway, "is_provider_available", lambda _name: False)

    result = gateway.ask("Explain a general concept", routing_text="general question")

    assert result["status"] == "error"
    assert result["error"]["code"] == "NO_PROVIDER_AVAILABLE"
    assert "dummy" not in result["provider_chain"]


def test_openrouter_maps_connection_exception_to_a_typed_network_error(monkeypatch):
    def raise_connection_error(*_args, **_kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("lab_v4_dev.llm.openrouter_provider.requests.post", raise_connection_error)
    response = OpenRouterProvider().execute(LLMRequest(prompt="test"))

    assert response.status == "error"
    assert response.error.code == "CONNECTION_ERROR"


def test_common_greeting_is_answered_locally_without_gateway_or_orchestrator(monkeypatch):
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a covered greeting must not call the provider gateway")
        ),
    )
    orchestrator = DialogueOnlyOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("مرحبا")

    assert result["status"] == "success"
    assert result["source"] == "local_social"
    assert "مرحبًا" in result["text"]
    assert orchestrator.calls == []


def test_expanded_friendly_dialogue_uses_local_engine_before_gateway(monkeypatch):
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("covered friendly dialogue must not call the provider gateway")
        ),
    )
    orchestrator = DialogueOnlyOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    cases = (
        ("شكرا جزيلا", "على الرحب والسعة"),
        ("اشعر بالملل", "تغيير الجو"),
        ("انا حزينة", "يومك ليس سهلًا"),
        ("مع السلامة", "إلى اللقاء"),
    )
    for phrase, expected in cases:
        result = manager.process(phrase)
        assert result["status"] == "success", phrase
        assert result["source"] == "local_dialogue_engine", phrase
        assert expected in result["text"], phrase
        assert result["executed"] is False, phrase

    assert orchestrator.calls == []


def test_topic_suggestions_use_the_single_local_responder_in_standard_arabic(monkeypatch):
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local topic suggestions must not call the provider")
        ),
    )
    orchestrator = DialogueOnlyOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("اقترح لي بعض المواضيع")

    assert result["status"] == "success"
    assert result["source"] == "local_dialogue_engine"
    assert "إليك بعض الموضوعات" in result["text"]
    assert "واش" not in result["text"]
    assert "شنو" not in result["text"]
    assert result["executed"] is False
    assert orchestrator.calls == []
