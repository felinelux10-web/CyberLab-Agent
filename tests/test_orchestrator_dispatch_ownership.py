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
        Intent.PROJECT_INDEX,
        Intent.SEARCH,
        Intent.SEARCH_CODE,
        Intent.DEPENDENCY_MAP,
        Intent.ENTRY_POINT_QUERY,
        Intent.DEPENDENTS_QUERY,
        Intent.DEPENDENCIES,
        Intent.IMPACT_CHAIN_QUERY,
        Intent.CRITICALITY_QUERY,
        Intent.IMPACT_ANALYSIS,
        Intent.FILE_IMPACT,
        Intent.COMPARE_FILES,
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


def test_project_index_counts_unique_registered_projects(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.project_registry.project_loader as loader_module

    monkeypatch.setattr(loader_module, "list_registered_projects", lambda: [
        {"name": "one", "root": "/projects/one"},
        {"name": "one-copy", "root": "/projects/one"},
        {"name": "two", "root": "/projects/two"},
    ])
    result = Orchestrator._route(_fake_orchestrator(), Intent.PROJECT_INDEX, "", None, "عدد المشاريع")
    assert result["status"] == "success"
    assert result["text"] == "عدد المشاريع المسجلة: 2"


def test_project_index_default_route_returns_layer_map(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.project_index as index_module

    monkeypatch.setattr(index_module, "get_layer_map", lambda: {"core": ["a.py", "b.py"]})
    result = Orchestrator._route(_fake_orchestrator(), Intent.PROJECT_INDEX, "", None, "خريطة المشروع")
    assert result["status"] == "success"
    assert "خريطة المشروع:" in result["text"]
    assert "core" in result["text"]
    assert "2 ملف" in result["text"]


def test_search_handler_reads_inventory_and_returns_matching_files(monkeypatch):
    import builtins
    import io
    import json
    from lab_v4_dev.core.orchestrator import Orchestrator

    inventory = {"files": [
        {"path": "core/agent.py", "filename": "agent.py"},
        {"path": "core/orchestrator.py", "filename": "orchestrator.py"},
    ]}
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: io.StringIO(json.dumps(inventory)))
    result = Orchestrator._route(_fake_orchestrator(), Intent.SEARCH, "agent", None, "ابحث عن agent")
    assert result["status"] == "success"
    assert "core/agent.py" in result["text"]


def test_search_handler_reports_missing_inventory_match(monkeypatch):
    import builtins
    import io
    import json
    from lab_v4_dev.core.orchestrator import Orchestrator

    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: io.StringIO(json.dumps({"files": []})))
    result = Orchestrator._route(_fake_orchestrator(), Intent.SEARCH, "not-there", None, "ابحث عن not-there")
    assert result["status"] == "success"
    assert "غير موجود" in result["text"]


def _prepare_search_code_project(monkeypatch, tmp_path):
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.awareness.project_index as index_module

    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    index_dir = root / ".index"
    index_dir.mkdir()
    (index_dir / "project_index.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(project_module, "get_active_project_root", lambda: str(root))
    monkeypatch.setattr(project_module, "project_index_dir", lambda active_root: str(index_dir))
    return root, index_module


def test_search_code_explicit_path_uses_filesystem_and_local_index(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator

    root, index_module = _prepare_search_code_project(monkeypatch, tmp_path)
    monkeypatch.setattr(index_module, "search_index", lambda query: [])
    monkeypatch.setattr(index_module, "save_index", lambda: None)

    result = Orchestrator._route(
        _fake_orchestrator(), Intent.SEARCH_CODE, "src/main.py", None,
        "ابحث عن src/main.py",
    )
    assert result["status"] == "success"
    assert result["source"] == "local_index+filesystem"
    assert result["target"] == "src/main.py"
    assert result["evidence"] == "filesystem_check_and_project_index"


def test_search_code_provider_call_remains_behind_authorized_ask(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.project_index as index_module
    import lab_v4_dev.llm.prompt_builder as prompt_module

    _prepare_search_code_project(monkeypatch, tmp_path)
    monkeypatch.setattr(index_module, "search_index", lambda query: [
        {"path": "src/main.py", "role": "entry", "score": 1},
    ])
    monkeypatch.setattr(prompt_module, "build_search_prompt", lambda query, results: "prompt")
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)

    result = Orchestrator._route(
        _fake_orchestrator(), Intent.SEARCH_CODE, "", None,
        "ابحث عن ملفات التشغيل",
        route_decision=decision,
    )
    assert result["status"] == "success"
    assert "src/main.py" in result["text"]


def test_dependency_map_uses_existing_index_and_returns_critical_and_orphan_files(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.awareness.dependency_map as map_module

    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "dependency_map.json").write_text("{}", encoding="utf-8")
    project = SimpleNamespace(index_dir=lambda: str(index_dir))
    monkeypatch.setattr(project_module, "get_active_project", lambda: project)
    monkeypatch.setattr(map_module, "get_critical_files", lambda: [{"file": "core.py", "used_by": 4}])
    monkeypatch.setattr(map_module, "get_orphans", lambda: ["unused.py"])

    result = Orchestrator._route(_fake_orchestrator(), Intent.DEPENDENCY_MAP, "", None, "")
    assert result["status"] == "success"
    assert "core.py" in result["text"]
    assert "unused.py" in result["text"]


def test_entry_point_query_returns_entry_points_and_critical_files(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.dependency_engine as engine_module

    monkeypatch.setattr(engine_module, "index_missing", lambda: False)
    monkeypatch.setattr(engine_module, "get_entry_points", lambda: ["run.py"])
    monkeypatch.setattr(engine_module, "get_critical_files", lambda: ["core.py"])
    result = Orchestrator._route(_fake_orchestrator(), Intent.ENTRY_POINT_QUERY, "", None, "")
    assert "run.py" in result["text"]
    assert "core.py" in result["text"]


def test_dependents_query_uses_dependency_engine(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.dependency_engine as engine_module

    monkeypatch.setattr(engine_module, "who_depends_on", lambda path: ["a.py", "b.py"])
    result = Orchestrator._route(_fake_orchestrator(), Intent.DEPENDENTS_QUERY, "", None, "من يستورد core.py")
    assert "a.py" in result["text"] and "b.py" in result["text"]


def test_dependencies_query_uses_dependency_engine(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.dependency_engine as engine_module

    monkeypatch.setattr(engine_module, "what_imports", lambda path: ["os", "pathlib"])
    result = Orchestrator._route(_fake_orchestrator(), Intent.DEPENDENCIES, "", None, "ما اعتمادات core.py")
    assert "os" in result["text"] and "pathlib" in result["text"]


def test_impact_chain_query_preserves_direct_and_indirect_results(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.dependency_engine as engine_module

    monkeypatch.setattr(engine_module, "get_impact_chain", lambda path: {
        "direct": ["a.py"], "indirect": ["b.py", "c.py"], "total_affected": 3,
    })
    result = Orchestrator._route(_fake_orchestrator(), Intent.IMPACT_CHAIN_QUERY, "", None, "حلل تأثير core.py")
    assert "a.py" in result["text"]
    assert "b.py" in result["text"]
    assert "إجمالي الملفات المتأثرة: 3" in result["text"]


def test_criticality_query_preserves_risk_report(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.query_engine as query_module

    monkeypatch.setattr(query_module, "query_file", lambda path: {
        "risk_score": 75, "risk_level": "high",
        "direct_dependencies": ["a.py"], "indirect_dependencies": ["b.py"],
        "total_affected": 2, "is_entry_point": True,
    })
    result = Orchestrator._route(_fake_orchestrator(), Intent.CRITICALITY_QUERY, "", None, "ما خطورة core.py")
    assert "75/100" in result["text"]
    assert "نقطة دخول رئيسية" in result["text"]


def test_impact_analysis_records_analyzed_target(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.planner.impact_analyzer as impact_module

    monkeypatch.setattr(impact_module, "analyze_impact", lambda target: {"files": ["a.py"]})
    orchestrator = _fake_orchestrator()
    orchestrator._impact_analyzed = set()
    result = Orchestrator._route(orchestrator, Intent.IMPACT_ANALYSIS, "core.py", None, "")
    assert result["status"] == "success"
    assert result["impact"] == {"files": ["a.py"]}
    assert "core.py" in orchestrator._impact_analyzed


def test_file_impact_specialized_dependency_question_keeps_priority(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.dependency_map as map_module
    import lab_v4_dev.core.project_context as project_module

    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "dependency_map.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(project_module, "get_active_project_root", lambda: str(tmp_path))
    monkeypatch.setattr(project_module, "project_index_dir", lambda root: str(index_dir))
    monkeypatch.setattr(map_module, "get_impact", lambda query: {"imported_by": ["consumer.py"]})

    result = Orchestrator._route(
        _fake_orchestrator(), Intent.FILE_IMPACT, "core.py", None,
        "من يستورد core.py",
    )
    assert result["status"] == "success"
    assert "الملفات التي تعتمد على core.py" in result["text"]
    assert "consumer.py" in result["text"]


def test_file_impact_general_question_keeps_full_impact_report(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.dependency_map as map_module
    import lab_v4_dev.core.project_context as project_module

    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "dependency_map.json").write_text("{}", encoding="utf-8")
    project = type("Project", (), {"root": str(tmp_path)})()
    monkeypatch.setattr(project_module, "get_active_project", lambda: project)
    monkeypatch.setattr(project_module, "get_active_project_root", lambda: str(tmp_path))
    monkeypatch.setattr(project_module, "project_index_dir", lambda root: str(index_dir))
    monkeypatch.setattr(project_module, "CYBERLAB_ROOT", str(tmp_path))
    monkeypatch.setattr(map_module, "get_impact", lambda query: {
        "file": "core.py", "risk": "high",
        "imports": ["os"], "imported_by": ["consumer.py"],
    })
    orchestrator = _fake_orchestrator()
    orchestrator._impact_analyzed = set()

    result = Orchestrator._route(
        orchestrator, Intent.FILE_IMPACT, "core.py", None,
        "ما تأثير تعديل core.py",
    )
    assert result["status"] == "success"
    assert "الخطورة: 🔴 high" in result["text"]
    assert "os" in result["text"]
    assert "consumer.py" in result["text"]
    assert "core.py" in orchestrator._impact_analyzed


def _prepare_compare_files(monkeypatch, tmp_path):
    import lab_v4_dev.core.project_context as project_module

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def alpha(): return 1", encoding="utf-8")
    (root / "b.py").write_text("def beta(): return 2", encoding="utf-8")
    monkeypatch.setattr(project_module, "get_active_project_root", lambda: str(root))
    return root


def test_compare_files_uses_authorized_provider_callback(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator

    _prepare_compare_files(monkeypatch, tmp_path)
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda prompt, **kwargs: {
            "status": "success", "text": "الفروق الرئيسية", "provider_used": "test-provider",
        },
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=True)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.COMPARE_FILES, "", None,
        "قارن بين a.py و b.py",
        route_decision=decision,
    )
    assert result["status"] == "success"
    assert result["source"] == "test-provider"
    assert result["text"] == "الفروق الرئيسية"


def test_compare_files_provider_denial_does_not_call_gateway(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator

    _prepare_compare_files(monkeypatch, tmp_path)
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.COMPARE_FILES, "", None,
        "قارن بين a.py و b.py",
        route_decision=decision,
    )
    assert result["status"] == "unavailable"
