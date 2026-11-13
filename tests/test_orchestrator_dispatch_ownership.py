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


def _fake_orchestrator():
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator

    orchestrator = object.__new__(Orchestrator)
    orchestrator.agent = SimpleNamespace(
        state=SimpleNamespace(mode="test", consecutive_failures=2),
        session=SimpleNamespace(summary=lambda: {
            "tasks_done": 7, "error_count": 1,
        }),
    )
    return orchestrator


def test_route_delegates_space_to_registered_handler():
    from lab_v4_dev.core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()
    result = Orchestrator._route(orchestrator, Intent.SPACE, None, None, "")
    assert result["status"] == "success"
    assert result["intent"] == Intent.SPACE
    assert {"total", "used", "free"} <= result.keys()


def test_route_delegates_status_without_changing_result_contract():
    from lab_v4_dev.core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()
    result = Orchestrator._route(orchestrator, Intent.STATUS, None, None, "")
    assert result == {
        "status": "success", "intent": Intent.STATUS,
        "text": chr(10).join(["الوضع     : test", "المهام    : 7", "الأخطاء   : 1", "الإخفاقات : 2"]),
        "mode": "test", "failures": 2, "tasks": 7, "errors": 1,
    }


def test_route_delegates_health_and_system_status(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.monitor.health_check as health_module

    calls = []
    monkeypatch.setattr(health_module, "check_health", lambda state: calls.append(state) or {
        "healthy": True, "state_mode": "test", "ram_ok": True,
        "ram_mb": 123, "db_ok": True, "log_ok": True,
        "stable_status": "ok",
    })
    orchestrator = _fake_orchestrator()

    health = Orchestrator._route(orchestrator, Intent.HEALTH, None, None, "")
    system = Orchestrator._route(orchestrator, Intent.SYSTEM_STATUS, None, None, "")

    assert health["health"]["healthy"] is True
    assert system["health"]["healthy"] is True
    assert "حالة النظام: سليم" in system["text"]
    assert len(calls) == 2


def test_route_delegates_memory_status(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.orchestrator_handlers.system_inspection as handler_module

    monkeypatch.setattr(handler_module, "load_memory", lambda: {
        "total_files": 19, "last_updated": "test-time",
    })
    result = Orchestrator._route(_fake_orchestrator(), Intent.MEMORY_STATUS, None, None, "")
    assert result == {
        "status": "success", "intent": Intent.MEMORY_STATUS,
        "total_files": 19, "last_updated": "test-time",
    }


def test_response_cache_precedes_health_handler(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.intent.response_cache as cache_module
    import lab_v4_dev.monitor.health_check as health_module

    monkeypatch.setattr(cache_module, "get", lambda intent, target: "cached-health")
    monkeypatch.setattr(
        health_module, "check_health",
        lambda state: (_ for _ in ()).throw(AssertionError("handler must not run before cache")),
    )
    result = Orchestrator._route(_fake_orchestrator(), Intent.HEALTH, None, None, "")
    assert result == {
        "status": "success", "intent": Intent.HEALTH,
        "source": "cache", "text": "cached-health",
    }
