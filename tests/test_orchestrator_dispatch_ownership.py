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
        Intent.AUDIT_LOG,
        Intent.SECURITY_LOG,
        Intent.READ_FILE,
        Intent.PROJECT_SCAN,
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
    assert dispatch(object(), Intent.UNKNOWN) is None


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
    assert chr(10) in system["text"]
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


def test_route_delegates_audit_log(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.audit as audit_module
    import lab_v4_dev.core.safe_io as safe_io_module

    monkeypatch.setattr(audit_module, "get_events", lambda limit: [{
        "event": "file.updated", "source": "test", "timestamp": "2026-11-13T07:00:00",
        "context": {"file_path": "demo.py"}, "details": {"reason": "test"},
    }])
    result = Orchestrator._route(_fake_orchestrator(), Intent.AUDIT_LOG, None, None, "")
    assert result["status"] == "success"
    assert "file.updated [test]" in result["text"]
    assert "demo.py" in result["text"]


def test_route_delegates_security_log(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.security_guard as security_module

    monkeypatch.setattr(security_module, "get_security_log", lambda limit: [{
        "timestamp": "2026-11-13T07:00:00", "type": "test", "value": "blocked value",
        "matched": "policy",
    }])
    result = Orchestrator._route(_fake_orchestrator(), Intent.SECURITY_LOG, None, None, "")
    assert result["status"] == "success"
    assert "blocked value" in result["text"]
    assert "تطابق: policy" in result["text"]


def test_route_delegates_read_file_using_project_index_candidate(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.project_index as index_module
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.core.audit as audit_module

    project_root = tmp_path / "project"
    source = project_root / "src" / "inside.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('inside')", encoding="utf-8")
    monkeypatch.setattr(project_module, "get_active_project_root", lambda: str(project_root))
    monkeypatch.setattr(index_module, "search_index", lambda target: [{"path": "src/inside.py"}])
    monkeypatch.setattr(audit_module, "emit_event", lambda *args, **kwargs: None)

    result = Orchestrator._route(_fake_orchestrator(), Intent.READ_FILE, "inside.py", None, "")
    assert result["status"] == "success"
    assert result["file"] == str(source)
    assert result["output"] == "print('inside')"


def test_read_file_rejects_project_index_candidate_outside_active_root(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.project_index as index_module
    import lab_v4_dev.core.project_context as project_module

    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(project_module, "get_active_project_root", lambda: str(project_root))
    monkeypatch.setattr(index_module, "search_index", lambda target: [{"path": "../outside.py"}])

    result = Orchestrator._route(_fake_orchestrator(), Intent.READ_FILE, "missing.py", None, "")
    assert result["status"] == "failed"
    assert "غير موجود" in result["message"]


def test_project_scan_registered_project_count_uses_unique_roots(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.project_registry.project_loader as loader_module

    monkeypatch.setattr(loader_module, "list_registered_projects", lambda: [
        {"name": "one", "root": "/projects/one"},
        {"name": "one-alias", "root": "/projects/one"},
        {"name": "two", "root": "/projects/two"},
        {"name": "invalid", "root": ""},
    ])
    result = Orchestrator._route(_fake_orchestrator(), Intent.PROJECT_SCAN, "", None, "كم مشروع")
    assert result == {
        "status": "success", "intent": Intent.PROJECT_SCAN,
        "source": "local", "text": "عدد المشاريع المسجلة: 2",
    }


def test_project_scan_returns_local_snapshot_and_audit_event(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.dependency_engine as dependency_module
    import lab_v4_dev.awareness.project_index as index_module
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.core.project_metadata as metadata_module
    import lab_v4_dev.core.audit as audit_module

    monkeypatch.setattr(dependency_module, "get_snapshot", lambda: {"total_files": 3})
    monkeypatch.setattr(dependency_module, "get_entry_points", lambda: ["run.py"])
    monkeypatch.setattr(dependency_module, "get_critical_files", lambda: ["a.py", "b.py"])
    monkeypatch.setattr(index_module, "get_layer_map", lambda: {"core": ["a.py", "b.py"], "ui": ["c.py"]})
    monkeypatch.setattr(project_module, "get_active_project", lambda: SimpleNamespace(name="demo", root="/projects/demo"))
    monkeypatch.setattr(metadata_module, "ProjectMetadata", lambda: SimpleNamespace(get_version=lambda: "1.2"))
    events = []
    monkeypatch.setattr(audit_module, "emit_event", lambda *args, **kwargs: events.append((args, kwargs)))

    result = Orchestrator._route(_fake_orchestrator(), Intent.PROJECT_SCAN, "", None, "افحص المشروع")
    assert result["status"] == "success"
    assert result["source"] == "local"
    assert result["total_files"] == 3
    assert result["critical"] == ["a.py", "b.py"]
    assert "المشروع: demo" in result["text"]
    assert "الإصدار: 1.2" in result["text"]
    assert len(events) == 1
    assert events[0][0][0] == "project.scan"
