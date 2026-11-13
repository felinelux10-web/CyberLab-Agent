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
        Intent.SEARCH_CODE, Intent.READ_EXTERNAL_PROJECT,
        Intent.DEPENDENCY_MAP,
        Intent.ENTRY_POINT_QUERY,
        Intent.DEPENDENTS_QUERY,
        Intent.DEPENDENCIES,
        Intent.IMPACT_CHAIN_QUERY,
        Intent.CRITICALITY_QUERY,
        Intent.IMPACT_ANALYSIS,
        Intent.FILE_IMPACT,
        Intent.COMPARE_FILES,
        Intent.REPORT, Intent.SESSION_REPORT, Intent.PROGRESS_REPORT,
        Intent.REMAINING_WORK, Intent.PROJECT_REPORT, Intent.CONTEXT_REPORT,
        Intent.HISTORY, Intent.WORK_STATUS, Intent.REMAINING_TASKS,
        Intent.NEXT_TASK, Intent.WORK_CONTEXT, "show_last_result",
        Intent.CAPABILITIES, Intent.SAVE_KB, Intent.SKIP_KB, Intent.CYBER_EXPLAIN,
        Intent.LAST_PROJECT,
        Intent.CURRENT_VERSION,
        Intent.RELEASE_INDEX,
        Intent.ANALYZE_RELEASE,
        Intent.COMPARE_VERSIONS,
        Intent.PROJECT_TIMELINE, Intent.SWITCH_PROJECT, Intent.RETURN_BASE_PROJECT,
        Intent.RESUME, Intent.SESSION_RESTORE, Intent.SESSION_SAVE,
        Intent.LIST_SCRIPTS,
        Intent.ERROR_REPORT,
        Intent.DRY_RUN,
        Intent.RUN_HISTORY, Intent.ANALYZE_CODE, Intent.GENERATE_CODE,
        Intent.SHOW_CHANGES, Intent.CLEAN, Intent.CLEANUP_CODE,
        Intent.PLAN_CHANGE, Intent.REPAIR_REJECT, Intent.PENDING_FIXES,
        Intent.SELF_DIAGNOSE, Intent.FULL_DIAGNOSE, Intent.CLEAN_DEVICE,
        Intent.DELETE_FILE, Intent.MODIFY_CODE, Intent.RUN_SCRIPT,
        Intent.REPAIR_ANALYZE, Intent.REPAIR_APPROVE,
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
        memory=SimpleNamespace(recent_tasks=lambda limit: []),
    )
    orchestrator.context = SimpleNamespace(last_result=None)
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


def test_session_report_keeps_current_session_summary_contract():
    from lab_v4_dev.core.orchestrator import Orchestrator

    result = Orchestrator._route(_fake_orchestrator(), Intent.REPORT, "", None, "")
    assert result["status"] == "success"
    assert result["intent"] == Intent.REPORT
    assert result["session"] == {"tasks_done": 7, "error_count": 1}
    assert len(result["time"]) == 16


def test_project_report_provider_permission_is_enforced(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator

    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.PROJECT_REPORT, "", None, "اكتب تقرير المشروع",
        route_decision=decision,
    )
    assert result["status"] == "unavailable"


def test_context_report_keeps_project_metadata_and_task_snapshot(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_metadata as metadata_module
    import lab_v4_dev.core.project_context as project_module

    releases = tmp_path / "releases"
    (releases / "v1").mkdir(parents=True)
    monkeypatch.setattr(project_module, "CYBERLAB_ROOT", str(tmp_path))
    monkeypatch.setattr(metadata_module, "ProjectMetadata", lambda: SimpleNamespace(
        get_current_phase=lambda: {"name": "phase-a"},
        get_version=lambda: "1.0",
        get_project_name=lambda: "demo",
    ))
    orchestrator = _fake_orchestrator()
    orchestrator.agent.memory.recent_tasks = lambda limit: [{"status": "success", "intent": "READ_FILE"}]
    result = Orchestrator._route(orchestrator, Intent.CONTEXT_REPORT, "", None, "")
    assert result["version"] == "1.0"
    assert result["focus"] == "demo"
    assert result["releases"] == ["v1"]
    assert result["tasks"][0]["intent"] == "READ_FILE"


def test_history_report_reads_recent_tasks():
    from lab_v4_dev.core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()
    orchestrator.agent.memory.recent_tasks = lambda limit: [{"status": "success", "intent": "SEARCH"}]
    result = Orchestrator._route(orchestrator, Intent.HISTORY, "", None, "")
    assert result["tasks"] == [{"status": "success", "intent": "SEARCH"}]


def test_work_tracking_handlers_keep_three_output_modes(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.data.work_tracker as tracker_module

    monkeypatch.setattr(tracker_module, "get_status", lambda: {
        "version": "1.0", "current_focus": "testing",
        "completed": ["A"], "active": ["B"], "planned": ["C"], "blocked": ["D"],
    })
    monkeypatch.setattr(tracker_module, "get_next_task", lambda: "B")
    monkeypatch.setattr(tracker_module, "get_remaining", lambda: ["B", "C"])

    work = Orchestrator._route(_fake_orchestrator(), Intent.WORK_STATUS, "", None, "")
    next_task = Orchestrator._route(_fake_orchestrator(), Intent.NEXT_TASK, "", None, "")
    remaining = Orchestrator._route(_fake_orchestrator(), Intent.REMAINING_TASKS, "", None, "")
    assert "الإصدار: 1.0" in work["text"] and "محظور" in work["text"]
    assert "المهمة التالية: B" == next_task["text"]
    assert "B" in remaining["text"] and "C" in remaining["text"]


def test_work_context_reports_live_tasks_and_pending_repairs(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.repair.diff_approval as approval_module

    orchestrator = _fake_orchestrator()
    orchestrator.agent.memory.recent_tasks = lambda limit: [
        {"status": "success", "intent": "READ_FILE", "plan": "read project file"},
    ]
    monkeypatch.setattr(approval_module, "list_pending", lambda: [{"fix": "repair.py"}])
    result = Orchestrator._route(orchestrator, Intent.WORK_CONTEXT, "", None, "")
    assert "read project file" in result["text"]
    assert "repair.py" in result["text"]


def test_show_last_result_uses_context_last_result():
    from lab_v4_dev.core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()
    orchestrator.context.last_result = {"text": "previous output"}
    result = Orchestrator._route(orchestrator, "show_last_result", "", None, "")
    assert result["text"] == "previous output"


def test_needs_llm_fallback_remains_explicit_and_provider_gated(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator

    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    import lab_v4_dev.llm.prompt_builder as prompt_module
    import lab_v4_dev.awareness.knowledge_retriever as retriever_module
    monkeypatch.setattr(prompt_module, "build_project_context", lambda **kwargs: "test context")
    monkeypatch.setattr(retriever_module, "resolve_project_scope", lambda *args, **kwargs: None)
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.ARCHITECTURE, "", None,
        "اشرح معمارية النظام",
        route_decision=decision,
    )
    assert result["status"] == "unavailable"
    assert result["intent"] == Intent.ARCHITECTURE


def test_capabilities_handler_reports_active_project_and_memory(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.awareness.project_memory as memory_module

    monkeypatch.setattr(project_module, "get_active_project", lambda: SimpleNamespace(name="demo"))
    monkeypatch.setattr(memory_module, "load_memory", lambda: {"total_files": 17})
    result = Orchestrator._route(_fake_orchestrator(), Intent.CAPABILITIES, "", None, "")
    assert result["status"] == "success"
    assert result["source"] == "local"
    assert "demo (17 ملف)" in result["text"]


def test_save_kb_persists_only_confirmed_pending_explanation(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.knowledge_base as knowledge_module

    calls = []
    monkeypatch.setattr(knowledge_module, "store", lambda *args, **kwargs: calls.append((args, kwargs)))
    orchestrator = _fake_orchestrator()
    orchestrator.context.pending_save = "topic"
    orchestrator.context.last_result = {"text": "verified explanation"}
    result = Orchestrator._route(orchestrator, Intent.SAVE_KB, "", None, "")
    assert result["status"] == "success"
    assert calls == [(("topic", "verified explanation"), {"confirmed": True, "confidence": "EXPLICIT"})]
    assert orchestrator.context.pending_save is None


def test_skip_kb_clears_pending_confirmation_without_writing(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.knowledge_base as knowledge_module

    monkeypatch.setattr(
        knowledge_module, "store",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("skip must not write")),
    )
    orchestrator = _fake_orchestrator()
    orchestrator.context.pending_save = "topic"
    result = Orchestrator._route(orchestrator, Intent.SKIP_KB, "", None, "")
    assert result["status"] == "success"
    assert orchestrator.context.pending_save is None


def test_cyber_explain_uses_local_knowledge_before_provider(monkeypatch):
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.knowledge_base as knowledge_module

    calls = []
    monkeypatch.setattr(knowledge_module, "search", lambda raw: "cached explanation")
    monkeypatch.setattr(knowledge_module, "hit", lambda raw: calls.append(raw))
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("local cache should win")),
    )
    orchestrator = _fake_orchestrator()
    result = Orchestrator._route(
        orchestrator, Intent.CYBER_EXPLAIN, "", None, "اشرح HTTP",
        response_attributes=None, conversation_history=[], context_transition=None,
    )
    assert result["source"] == "local_kb"
    assert "cached explanation" in result["text"]
    assert orchestrator.context.current_subject == "اشرح HTTP"
    assert calls == ["اشرح HTTP"]


def test_cyber_explain_provider_denial_is_enforced(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.knowledge_base as knowledge_module
    import lab_v4_dev.llm.prompt_builder as prompt_module

    monkeypatch.setattr(knowledge_module, "search", lambda raw: None)
    monkeypatch.setattr(prompt_module, "build_cybersec_prompt", lambda *args, **kwargs: ("system", "prompt"))
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.CYBER_EXPLAIN, "", None, "اشرح HTTP",
        route_decision=decision, response_attributes=None,
        conversation_history=[], context_transition=None,
    )
    assert result["status"] == "unavailable"
    assert result["pending_save"] is None
    assert result["save_prompt"] is None


def test_cyber_explain_success_sets_pending_save_confirmation(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.knowledge_base as knowledge_module
    import lab_v4_dev.llm.prompt_builder as prompt_module

    monkeypatch.setattr(knowledge_module, "search", lambda raw: None)
    monkeypatch.setattr(prompt_module, "build_cybersec_prompt", lambda *args, **kwargs: ("system", "prompt"))
    monkeypatch.setattr(orchestrator_module, "ask", lambda *args, **kwargs: {
        "status": "success", "text": "verified explanation", "provider_used": "test-provider",
    })
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=True)
    orchestrator = _fake_orchestrator()
    result = Orchestrator._route(
        orchestrator, Intent.CYBER_EXPLAIN, "", None, "اشرح HTTP",
        route_decision=decision, response_attributes=None,
        conversation_history=[], context_transition=None,
    )
    assert result["status"] == "success"
    assert result["pending_save"] == "اشرح HTTP"
    assert result["pending_confirmation"]["kind"] == "save_kb"
    assert result["save_prompt"]
    assert orchestrator.context.current_subject == "اشرح HTTP"


def test_last_project_handler_returns_saved_project_history(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.project_knowledge as knowledge_module

    monkeypatch.setattr(knowledge_module, "get_project_history", lambda: {
        "last_project": "demo", "last_root": "/projects/demo",
        "history": [{"name": "demo", "last_used": "2026-11-13"}],
    })
    result = Orchestrator._route(_fake_orchestrator(), Intent.LAST_PROJECT, "", None, "")
    assert "آخر مشروع: demo" in result["text"]
    assert "/projects/demo" in result["text"]


def test_current_version_and_release_index_handlers(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_metadata as metadata_module
    import lab_v4_dev.awareness.release_analyzer as release_module

    monkeypatch.setattr(metadata_module, "ProjectMetadata", lambda: SimpleNamespace(get_version=lambda: "4.7"))
    monkeypatch.setattr(release_module, "get_available_versions", lambda: ["v4.6", "v4.7"])
    version = Orchestrator._route(_fake_orchestrator(), Intent.CURRENT_VERSION, "", None, "")
    index = Orchestrator._route(_fake_orchestrator(), Intent.RELEASE_INDEX, "", None, "")
    assert "4.7" in version["text"]
    assert index["versions"] == ["v4.6", "v4.7"]


def test_analyze_release_uses_authorized_provider_callback(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.release_analyzer as release_module
    import lab_v4_dev.llm.prompt_builder as prompt_module

    monkeypatch.setattr(release_module, "extract_version_from_text", lambda value: "v4.7")
    monkeypatch.setattr(release_module, "load_release", lambda version: {"content": "release notes"})
    monkeypatch.setattr(prompt_module, "build_release_prompt", lambda *args: "release prompt")
    monkeypatch.setattr(orchestrator_module, "ask", lambda *args, **kwargs: {
        "status": "success", "text": "release analysis", "provider_used": "test-provider",
    })
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=True)
    orchestrator = _fake_orchestrator()
    result = Orchestrator._route(
        orchestrator, Intent.ANALYZE_RELEASE, "", None, "حلل الإصدار 4.7",
        route_decision=decision,
    )
    assert result["version"] == "v4.7"
    assert result["source"] == "test-provider"
    assert orchestrator.context.current_version == "v4.7"
    assert orchestrator.context.current_subject == "version_v4.7"


def test_compare_versions_provider_denial_is_enforced(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.awareness.release_analyzer as release_module

    monkeypatch.setattr(release_module, "compare_versions", lambda v1, v2: {
        "both_ok": True, "v1": {"content": "one"}, "v2": {"content": "two"},
    })
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.COMPARE_VERSIONS, "", None,
        "قارن بين 4.6 و 4.7",
        route_decision=decision,
    )
    assert result["status"] == "unavailable"


def test_project_timeline_uses_version_specific_events(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.data.project_timeline as timeline_module

    calls = []
    monkeypatch.setattr(timeline_module, "init_timeline", lambda: calls.append("init"))
    monkeypatch.setattr(timeline_module, "get_version_events", lambda version: [{"event": "released"}])
    monkeypatch.setattr(timeline_module, "get_full_history", lambda: "all history")
    orchestrator = _fake_orchestrator()
    orchestrator.context.current_version = "v4.6"
    result = Orchestrator._route(orchestrator, Intent.PROJECT_TIMELINE, "", None, "")
    assert "أحداث v4.6" in result["text"]
    assert "released" in result["text"]
    assert calls == ["init"]


def test_switch_project_preserves_index_build_history_and_audit(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.core.project_metadata as metadata_module
    import lab_v4_dev.awareness.project_index as index_module
    import lab_v4_dev.awareness.project_knowledge as knowledge_module
    import lab_v4_dev.core.audit as audit_module
    import lab_v4_dev.awareness.project_reader as reader_module

    root = tmp_path / "next-project"
    root.mkdir()
    (root / "main.py").write_text("print('ok')", encoding="utf-8")
    index_dir = tmp_path / "index"
    calls = {"set": [], "history": [], "audit": []}

    monkeypatch.setattr(project_module, "get_active_project", lambda: SimpleNamespace(name="old", root="/projects/old"))
    monkeypatch.setattr(project_module, "set_active_project", lambda path: (
        calls["set"].append(path) or {
            "status": "success",
            "project": {"name": "next-project", "root": str(root)},
        }
    ))
    monkeypatch.setattr(project_module, "project_index_dir", lambda path: str(index_dir))

    class FakeReader:
        def scan_files(self): calls.setdefault("scan", 0); calls["scan"] += 1
        def build_graph(self): calls.setdefault("graph", 0); calls["graph"] += 1
        def generate_outputs(self): calls.setdefault("outputs", 0); calls["outputs"] += 1

    monkeypatch.setattr(reader_module, "ProjectReader", FakeReader)
    monkeypatch.setattr(index_module, "save_index", lambda: calls.setdefault("save_index", 0))
    monkeypatch.setattr(knowledge_module, "get_project_history", lambda: {
        "last_project": "old", "last_root": "/projects/old", "history": [],
    })
    monkeypatch.setattr(knowledge_module, "save_project_history", lambda value: calls["history"].append(value))
    monkeypatch.setattr(audit_module, "emit_event", lambda *args, **kwargs: calls["audit"].append((args, kwargs)))

    result = Orchestrator._route(_fake_orchestrator(), Intent.SWITCH_PROJECT, "", None, str(root))
    assert result["status"] == "success"
    assert calls["set"] == [str(root)]
    assert calls["scan"] == calls["graph"] == calls["outputs"] == 1
    assert calls["history"][0]["last_project"] == "next-project"
    assert calls["audit"][0][0][0] == "project.switched"


def test_return_base_project_uses_base_root_and_propagates_failure(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module

    base_root = str(tmp_path / "base")
    calls = []
    monkeypatch.setattr(project_module, "BASE_PROJECT_ROOT", base_root)
    monkeypatch.setattr(project_module, "get_active_project", lambda: SimpleNamespace(name="old", root="/old"))
    monkeypatch.setattr(project_module, "set_active_project", lambda path: (
        calls.append(path) or {"status": "failed", "message": "denied"}
    ))
    result = Orchestrator._route(_fake_orchestrator(), Intent.RETURN_BASE_PROJECT, "", None, "")
    assert calls == [base_root]
    assert result["status"] == "failed"
    assert result["text"] == "denied"


def test_session_save_persists_work_and_dialogue_records_separately(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.memory.session_state as session_module
    import lab_v4_dev.data.project_timeline as timeline_module

    calls = {"work": [], "dialogue": [], "events": []}
    monkeypatch.setattr(session_module, "save_session", lambda **kwargs: (
        calls["work"].append(kwargs) or {"session_id": "work-1", "active_goal": kwargs["active_goal"]}
    ))
    monkeypatch.setattr(session_module, "save_dialogue_checkpoint", lambda **kwargs: (
        calls["dialogue"].append(kwargs) or {"session_id": "dialogue-1", "active_goal": "conversation"}
    ))
    monkeypatch.setattr(timeline_module, "add_event", lambda *args: calls["events"].append(args))

    orchestrator = _fake_orchestrator()
    orchestrator.context.current_subject = "current goal"
    orchestrator.context.current_file = "main.py"
    orchestrator.context.get_last = lambda: {"topic": "current goal"}
    orchestrator.agent._meta = SimpleNamespace(get_version=lambda: "v1")
    orchestrator.agent.dialogue_memory = SimpleNamespace(snapshot=lambda: {"exchanges": []})

    result = Orchestrator._route(orchestrator, Intent.SESSION_SAVE, "", None, "")
    assert result["status"] == "success"
    assert result["work_session_id"] == "work-1"
    assert result["dialogue_session_id"] == "dialogue-1"
    assert calls["work"][0]["active_goal"] == "current goal"
    assert calls["dialogue"][0]["dialogue_state"] == {"exchanges": []}
    assert calls["events"][0][0] == "v1"


def test_list_scripts_uses_workspace_folders(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module

    workspace = tmp_path / "workspace"
    for folder, filename in [("scripts", "a.py"), ("modified", "b.py"), ("analysis", "c.txt")]:
        directory = workspace / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / filename).write_text("x", encoding="utf-8")
    monkeypatch.setattr(project_module, "CYBERLAB_ROOT", str(tmp_path))
    result = Orchestrator._route(_fake_orchestrator(), Intent.LIST_SCRIPTS, "", None, "")
    assert result["status"] == "success"
    assert "scripts/a.py" in result["text"]
    assert "modified/b.py" in result["text"]
    assert "analysis/c.txt" in result["text"]


def test_error_report_handler_formats_recent_errors(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.sandbox_executor as sandbox_module

    monkeypatch.setattr(sandbox_module, "list_error_reports", lambda: [
        {"approved": False, "file": "bad.py", "error": "SyntaxError"},
    ])
    result = Orchestrator._route(_fake_orchestrator(), Intent.ERROR_REPORT, "", None, "")
    assert result["status"] == "success"
    assert "bad.py" in result["text"]
    assert "SyntaxError" in result["text"]


def test_dry_run_handler_uses_latest_workspace_script(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.core.sandbox_executor as sandbox_module

    scripts = tmp_path / "workspace" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "latest.py").write_text("print('ok')", encoding="utf-8")
    monkeypatch.setattr(project_module, "CYBERLAB_ROOT", str(tmp_path))
    monkeypatch.setattr(sandbox_module, "dry_run", lambda path: {"status": "ok", "message": "safe"})
    result = Orchestrator._route(_fake_orchestrator(), Intent.DRY_RUN, "", None, "")
    assert result["status"] == "success"
    assert "latest.py" in result["text"]
    assert "safe" in result["text"]


def test_run_history_handler_uses_execution_history_service(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.execution_history as history_module

    monkeypatch.setattr(history_module, "get_history", lambda limit: [
        {"status": "success", "script": "/workspace/a.py", "duration": 1.2},
    ])
    result = Orchestrator._route(_fake_orchestrator(), Intent.RUN_HISTORY, "", None, "")
    assert result["status"] == "success"
    assert "a.py" in result["text"]


def test_analyze_code_vague_target_requests_clarification_without_provider(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.orchestrator as orchestrator_module

    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("vague request must not call provider")),
    )
    result = Orchestrator._route(_fake_orchestrator(), Intent.ANALYZE_CODE, "", None, "هذا الملف")
    assert result["status"] == "needs_clarification"
    assert "أي ملف" in result["text"]


def test_analyze_code_uses_authorized_provider_and_updates_context(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.intent.response_cache as cache_module

    source = tmp_path / "main.py"
    source.write_text("print('ok')", encoding="utf-8")
    cache_calls = []
    monkeypatch.setattr(cache_module, "save", lambda *args: cache_calls.append(args))
    monkeypatch.setattr(orchestrator_module, "ask", lambda *args, **kwargs: {
        "status": "success", "text": "analysis result", "provider_used": "test-provider",
    })
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=True)
    orchestrator = _fake_orchestrator()
    orchestrator._analyzed_files = set()
    result = Orchestrator._route(
        orchestrator, Intent.ANALYZE_CODE, str(source), None, "حلل هذا الملف",
        route_decision=decision,
    )
    assert result["status"] == "success"
    assert result["source"] == "test-provider"
    assert result["text"] == "analysis result"
    assert str(source) in orchestrator._analyzed_files
    assert orchestrator.context.current_subject == "حلل هذا الملف"
    assert cache_calls


def test_analyze_code_provider_denial_does_not_call_gateway(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator

    source = tmp_path / "main.py"
    source.write_text("print('ok')", encoding="utf-8")
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.ANALYZE_CODE, str(source), None, "حلل هذا الملف",
        route_decision=decision,
    )
    assert result["status"] == "unavailable"


def test_show_changes_reports_recent_operation_history():
    from lab_v4_dev.core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()
    orchestrator.agent.memory.recent_tasks = lambda limit: [
        {"status": "success", "intent": "READ_FILE"},
        {"status": "failed", "intent": "RUN_SCRIPT"},
    ]
    result = Orchestrator._route(orchestrator, Intent.SHOW_CHANGES, "", None, "")
    assert "آخر التعديلات" in result["text"]
    assert "✅ READ_FILE" in result["text"]
    assert "❌ RUN_SCRIPT" in result["text"]


def test_clean_intent_requests_scope_without_cleaning():
    from lab_v4_dev.core.orchestrator import Orchestrator

    result = Orchestrator._route(_fake_orchestrator(), Intent.CLEAN, "", None, "")
    assert result["status"] == "needs_clarification"
    assert "حدّد الهدف" in result["text"]


def test_cleanup_code_creates_review_only_plan(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.planner.planner as planner_module

    calls = []
    monkeypatch.setattr(planner_module, "Planner", lambda: SimpleNamespace(from_actions=lambda *args, **kwargs: (
        calls.append((args, kwargs)) or SimpleNamespace(to_dict=lambda: {"plan_id": kwargs["plan_id"]})
    )))
    result = Orchestrator._route(_fake_orchestrator(), Intent.CLEANUP_CODE, "src/", None, "")
    assert result["status"] == "needs_clarification"
    assert result["plan_only"] is True
    assert result["executed"] is False
    assert result["plan"]["plan_id"].startswith("cleanup-code-")


def test_plan_change_creates_preview_without_applying_edits(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.project_knowledge.analysis_engine as analysis_module
    import lab_v4_dev.dni.knowledge_router as router_module

    monkeypatch.setattr(analysis_module, "AnalysisEngine", lambda: SimpleNamespace(analyze_file=lambda path: None))
    plan = SimpleNamespace(steps=[
        SimpleNamespace(parameters={"file": "src/consumer.py", "priority": "high"}, action="review"),
    ])
    monkeypatch.setattr(router_module, "create_p10_plan_from_change", lambda *args, **kwargs: plan)
    result = Orchestrator._route(_fake_orchestrator(), Intent.PLAN_CHANGE, "", None, "خطط لتعديل src/core.py")
    assert result["status"] == "success"
    assert result["source"] == "pie"
    assert "src/consumer.py" in result["text"]
    assert "لا يتم أي تعديل" in result["text"]


def test_repair_reject_clears_last_result_without_file_changes():
    from lab_v4_dev.core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()
    orchestrator.context.last_result = {"pending": "fix"}
    result = Orchestrator._route(orchestrator, Intent.REPAIR_REJECT, "", None, "")
    assert result["status"] == "success"
    assert orchestrator.context.last_result is None
    assert "لم يتم تعديل أي شيء" in result["text"]


def test_pending_fixes_lists_only_pending_repairs(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.repair.diff_approval as approval_module

    monkeypatch.setattr(approval_module, "list_pending", lambda: [{"fix": "main.py"}])
    result = Orchestrator._route(_fake_orchestrator(), Intent.PENDING_FIXES, "", None, "")
    assert result["status"] == "success"
    assert "main.py" in result["text"]


def test_read_external_project_switches_scope_and_emits_audit(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module
    import lab_v4_dev.awareness.ts_reader as reader_module
    import lab_v4_dev.core.audit as audit_module

    root = tmp_path / "external"
    root.mkdir()
    calls = {"switch": [], "events": []}
    monkeypatch.setattr(project_module, "get_active_project", lambda: SimpleNamespace(root="/old"))
    monkeypatch.setattr(project_module, "set_active_project", lambda path: (
        calls["switch"].append(path) or {"status": "success", "project": {"root": path}}
    ))
    monkeypatch.setattr(reader_module, "scan_project", lambda path: {
        "project_type": "python", "total_files": 3,
        "entry_points": ["main.py"], "critical_files": ["main.py", "core.py"],
    })
    monkeypatch.setattr(audit_module, "emit_event", lambda *args, **kwargs: calls["events"].append((args, kwargs)))

    result = Orchestrator._route(_fake_orchestrator(), Intent.READ_EXTERNAL_PROJECT, "", None, str(root))
    assert result["status"] == "success"
    assert "تم قراءة المشروع" in result["text"]
    assert calls["switch"] == [str(root)]
    assert [event[0][0] for event in calls["events"]] == ["project.switched", "project.external_scan"]


def test_read_external_project_missing_path_does_not_switch(monkeypatch, tmp_path):
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.project_context as project_module

    calls = []
    monkeypatch.setattr(project_module, "set_active_project", lambda path: calls.append(path))
    missing = str(tmp_path / "missing")
    result = Orchestrator._route(_fake_orchestrator(), Intent.READ_EXTERNAL_PROJECT, "", None, missing)
    assert result["status"] == "success"
    assert missing in result["text"]
    assert calls == []


def test_generate_code_template_works_without_provider_permission(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.code_engine as engine_module

    monkeypatch.setattr(engine_module, "save_file", lambda code, filename, folder: "/workspace/scripts/template.py")
    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("template must not call provider")),
    )
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.GENERATE_CODE, "", None, "اكتب لعبة تخمين",
        route_decision=decision,
    )
    assert result["status"] == "success"
    assert result["saved_to"] == "/workspace/scripts/template.py"


def test_generate_code_non_template_requires_authorized_provider(monkeypatch):
    from types import SimpleNamespace
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    import lab_v4_dev.core.code_engine as engine_module

    monkeypatch.setattr(
        orchestrator_module, "ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider gate bypassed")),
    )
    monkeypatch.setattr(engine_module, "save_file", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not save without generated code")))
    decision = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = Orchestrator._route(
        _fake_orchestrator(), Intent.GENERATE_CODE, "", None, "اكتب دالة لمعالجة JSON",
        route_decision=decision,
    )
    assert result["status"] == "unavailable"


def test_handler_facade_exposes_scoped_services_without_agent_object():
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator_handlers.context import (
        HandlerContext, build_handler_facade,
    )

    state = object()
    session = object()
    memory = object()
    db = object()
    original = SimpleNamespace(
        agent=SimpleNamespace(state=state, session=session, memory=memory, db=db),
        context=object(),
        pipeline=None,
        _analyzed_files=set(),
        _impact_analyzed=set(),
        _get_pipeline=lambda: "pipeline",
    )

    status_facade = build_handler_facade(
        original, HandlerContext(intent=Intent.STATUS)
    )
    assert not hasattr(status_facade, "agent")
    assert status_facade.services.state is state
    assert status_facade.services.session is session
    assert status_facade.services.memory is None
    assert status_facade.services.db is None

    modify_facade = build_handler_facade(
        original, HandlerContext(intent=Intent.MODIFY_CODE)
    )
    assert not hasattr(modify_facade, "agent")
    assert modify_facade.services.db is db
    assert modify_facade.services.analyzed_files is original._analyzed_files
    assert modify_facade.services.impact_analyzed is original._impact_analyzed
    assert modify_facade._get_pipeline() == "pipeline"


def test_repository_has_no_legacy_orchestrator_execution_callers():
    from pathlib import Path
    import re

    root = Path(__file__).resolve().parents[1] / "lab_v4_dev"
    legacy_calls = []
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(source.splitlines(), 1):
            if re.search(r"(?:self\.)?orchestrator\.handle\s*\(", line):
                if path.name != "conversation_manager.py":
                    legacy_calls.append(f"{path.relative_to(root)}:{line_number}")
            if re.search(r"orchestrator\._route\s*\(", line):
                legacy_calls.append(f"{path.relative_to(root)}:{line_number}")
    assert legacy_calls == []


def test_domain_handlers_do_not_reach_agent_gateway_or_cli():
    from pathlib import Path
    import re

    root = Path(__file__).resolve().parents[1] / "lab_v4_dev/core/orchestrator_handlers"
    violations = []
    for path in root.glob("*.py"):
        if path.name in {"context.py", "services.py", "dispatch.py"}:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "orchestrator.agent" in source:
            violations.append(f"{path.name}: full Agent access")
        if re.search(r"(?<!authorized_)\bask\s*\(", source):
            violations.append(f"{path.name}: direct provider call")
        if re.search(r"^\s*(?:print|input)\s*\(", source, re.MULTILINE):
            violations.append(f"{path.name}: CLI interaction")
    assert violations == []
