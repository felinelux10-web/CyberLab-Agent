from types import MappingProxyType

import pytest

from lab_v4_dev.core.orchestrator_handlers.dispatch import (
    HANDLER_REGISTRY,
    build_registry,
    dispatch,
    registered_intents,
)
from lab_v4_dev.intent.intents import Intent


def test_read_only_pilot_intents_have_exactly_one_registered_owner():
    expected = {
        Intent.SPACE,
        Intent.STATUS,
        Intent.HEALTH,
        Intent.MEMORY_STATUS,
        Intent.SYSTEM_STATUS,
    }
    assert registered_intents() == expected
    assert isinstance(HANDLER_REGISTRY, MappingProxyType)
    assert len(HANDLER_REGISTRY) == len(expected)


def test_duplicate_handler_registration_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        build_registry(((Intent.STATUS, lambda *_: {}), (Intent.STATUS, lambda *_: {})))


def test_non_callable_handler_registration_is_rejected():
    with pytest.raises(TypeError, match="callable"):
        build_registry(((Intent.STATUS, None),))


def test_unregistered_intent_is_not_captured_by_a_default_handler():
    assert dispatch(object(), Intent.READ_FILE) is None


def test_dispatch_calls_the_registered_owner():
    class FakeOrchestrator:
        pass

    fake = FakeOrchestrator()
    result = dispatch(fake, Intent.SPACE)
    assert result["status"] == "success"
    assert result["intent"] == Intent.SPACE
    assert {"total", "used", "free"} <= result.keys()
