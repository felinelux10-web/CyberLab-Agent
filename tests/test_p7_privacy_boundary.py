from lab_v4_dev.llm import gateway


def test_prepare_request_sanitizes_system_as_well_as_prompt():
    request = gateway._prepare_request(
        "اشرح هذا",
        system="Authorization: Bearer supersecret_token_12345",
    )

    assert "supersecret_token_12345" not in request.system
    assert "[REDACTED:AUTH_HEADER]" in request.system


def test_secret_in_prompt_blocks_provider_routing(monkeypatch):
    provider_calls = []
    monkeypatch.setattr(
        gateway,
        "_provider_chain",
        lambda *_a, **_k: provider_calls.append(True) or ["dummy"],
    )

    result = gateway.ask("password=top_secret_value", routing_text="password")

    assert result["status"] == "error"
    assert result["error"]["code"] == "PRIVACY_EXTERNAL_BLOCKED"
    assert provider_calls == []
    assert result["metadata"]["privacy"]["allow_external"] is False


def test_secret_in_system_blocks_even_public_prompt(monkeypatch):
    provider_calls = []
    monkeypatch.setattr(
        gateway,
        "_provider_chain",
        lambda *_a, **_k: provider_calls.append(True) or ["dummy"],
    )

    result = gateway.ask("ما معنى CSRF؟", system="-----BEGIN PRIVATE KEY-----")

    assert result["status"] == "error"
    assert result["error"]["code"] == "PRIVACY_EXTERNAL_BLOCKED"
    assert provider_calls == []
