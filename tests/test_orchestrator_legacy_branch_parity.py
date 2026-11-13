import inspect

from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.core.orchestrator_handlers.dispatch import HANDLER_REGISTRY
from lab_v4_dev.core.orchestrator_handlers import project_analysis, reports
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.llm.router import needs_llm


LEGACY_ROUTE_INTENTS = frozenset({
    "analyze_code",
    "analyze_release",
    "audit_log",
    "capabilities",
    "clean",
    "clean_device",
    "cleanup_code",
    "compare_files",
    "compare_versions",
    "context_report",
    "criticality_query",
    "current_version",
    "cyber_explain",
    "delete_file",
    "dependencies",
    "dependency_map",
    "dependents_query",
    "dry_run",
    "entry_point_query",
    "error_report",
    "file_impact",
    "full_diagnose",
    "generate_code",
    "health",
    "history",
    "impact_analysis",
    "impact_chain_query",
    "last_project",
    "list_scripts",
    "memory_status",
    "modify_code",
    "next_task",
    "pending_fixes",
    "plan_change",
    "progress_report",
    "project_index",
    "project_report",
    "project_scan",
    "project_timeline",
    "read_external_project",
    "read_file",
    "release_index",
    "remaining_tasks",
    "remaining_work",
    "repair_analyze",
    "repair_approve",
    "repair_reject",
    "report",
    "resume",
    "return_base_project",
    "run_history",
    "run_script",
    "save_kb",
    "search",
    "search_code",
    "security_log",
    "self_diagnose",
    "session_report",
    "session_restore",
    "session_save",
    "show_changes",
    "show_last_result",
    "skip_kb",
    "space",
    "status",
    "switch_project",
    "system_status",
    "work_context",
    "work_status",
})


def test_current_registry_has_exact_legacy_branch_key_parity():
    assert set(HANDLER_REGISTRY) == LEGACY_ROUTE_INTENTS
    assert len(HANDLER_REGISTRY) == 69
    assert HANDLER_REGISTRY["show_last_result"] is reports.handle_show_last_result


def test_special_ordering_response_cache_registry_needs_llm_unsupported():
    source = inspect.getsource(Orchestrator._route)
    cache_gate = source.index("# ─── Response Cache")
    registry_dispatch = source.index("_dispatch_handler(")
    provider_fallback = source.index("if needs_llm(intent):")
    unsupported = source.index('"status"  : "unsupported"')

    assert cache_gate < registry_dispatch < provider_fallback < unsupported


def test_file_impact_specialized_reverse_dependency_mode_precedes_general_impact():
    source = inspect.getsource(project_analysis.handle_file_impact)
    specialized = source.index('if any(w in (raw or "")')
    general = source.index("else:", specialized)

    assert specialized < general
    assert "get_impact(q)" in source
    assert 'impact.get("imported_by", [])' in source


def test_show_last_result_is_read_only_and_needs_llm_remains_explicit():
    source = inspect.getsource(Orchestrator.handle)
    assert 'intent != "show_last_result" and not read_only_session_report' in source

    declared = {
        value for name, value in vars(Intent).items()
        if name.isupper() and isinstance(value, str)
    }
    llm_intents = {intent for intent in declared if needs_llm(intent)}
    assert len(llm_intents) == 19
    assert llm_intents - set(HANDLER_REGISTRY) == {
        "diagnose", "propose_solution", "propose_fix", "risk_analysis", "plan",
        "decompose", "refactor_file", "optimize_code", "generate_test",
        "project_purpose", "architecture", "modules", "execution_flow",
    }
