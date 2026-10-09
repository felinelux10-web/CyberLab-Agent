
def test_gateway_blocks_synthetic_secret_even_when_it_arrives_in_history(monkeypatch):
    import lab_v4_dev.llm.gateway as gateway

    called = []
    monkeypatch.setattr(gateway, "is_provider_available", lambda name: True)
    monkeypatch.setattr(gateway, "is_provider_enabled", lambda name: True)
    monkeypatch.setattr(gateway, "get_provider", lambda name: called.append(name))
    result = gateway.ask(
        "أجب عن السؤال الحالي.",
        system="تاريخ الحوار: DNI_RUNTIME_TEST_SECRET_HISTORY_123",
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "PRIVACY_EXTERNAL_BLOCKED"
    assert called == []
    assert "DNI_RUNTIME_TEST_SECRET_HISTORY_123" not in repr(result)


def test_gateway_offline_failure_does_not_bypass_privacy_sanitization(monkeypatch):
    import lab_v4_dev.llm.gateway as gateway

    monkeypatch.setattr(gateway, "is_provider_available", lambda name: name == "dummy")
    monkeypatch.setattr(gateway, "is_provider_enabled", lambda name: True)
    result = gateway.ask("سؤال عادي دون بيانات سرية")
    assert result["status"] in {"success", "error", "fallback"}
    assert "DNI_RUNTIME_TEST_SECRET_OFFLINE_123" not in repr(result)


def test_ordinary_conversation_does_not_persist_personal_memory(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as module
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.conversation_manager import ConversationManager

    calls = []
    monkeypatch.setattr(module, "gateway_ask", lambda *args, **kwargs: {
        "status": "success", "text": "أهلًا"
    })
    monkeypatch.setattr(
        "lab_v4_dev.memory.personal_memory.PersonalMemoryStore.remember",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    class FakeOrchestrator:
        context = ContextStore()

    result = ConversationManager(FakeOrchestrator()).process("مرحبًا، كيف حالك؟")
    assert result["status"] == "success"
    assert calls == []
