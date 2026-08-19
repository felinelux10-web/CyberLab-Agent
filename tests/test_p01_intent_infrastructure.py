from lab_v4_dev.intent.intent_contract import (
    IntentResolution,
    from_legacy,
    to_legacy,
)
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.semantic_router import route


def test_intent_resolution_contract():
    resolution = IntentResolution(
        intent="health",
        target=None,
        context=None,
        confidence=1.0,
    )

    assert resolution.intent == "health"
    assert resolution.confidence == 1.0


def test_legacy_adapter_roundtrip():
    legacy = {
        "intent": "health",
        "target": None,
        "context": None,
        "extra": "preserved",
    }

    resolution = from_legacy(legacy)
    restored = to_legacy(resolution)

    assert restored == legacy


def test_parser_is_available_as_canonical_boundary():
    result = parse("ما حالة النظام؟")

    assert isinstance(result, dict)
    assert "intent" in result
    assert "target" in result
    assert "context" in result


def test_intent_definition_remains_available():
    assert Intent is not None


def test_semantic_router_remains_available():
    assert callable(route)
