"""Explicit, duplicate-safe registry for migrated Orchestrator intents."""

from types import MappingProxyType

from lab_v4_dev.intent.intents import Intent
from . import system_inspection, project_inspection, project_analysis, reports


def build_registry(entries):
    registry = {}
    for intent, handler in entries:
        if intent in registry:
            raise ValueError(f"duplicate Orchestrator handler registration: {intent!r}")
        if not callable(handler):
            raise TypeError(f"handler for {intent!r} must be callable")
        registry[intent] = handler
    return MappingProxyType(registry)


HANDLER_REGISTRY = build_registry((
    (Intent.SPACE, system_inspection.handle_space),
    (Intent.STATUS, system_inspection.handle_status),
    (Intent.HEALTH, system_inspection.handle_health),
    (Intent.MEMORY_STATUS, system_inspection.handle_memory_status),
    (Intent.SYSTEM_STATUS, system_inspection.handle_system_status),
    (Intent.AUDIT_LOG, system_inspection.handle_audit_log),
    (Intent.SECURITY_LOG, system_inspection.handle_security_log),
    (Intent.READ_FILE, project_inspection.handle_read_file),
    (Intent.PROJECT_SCAN, project_inspection.handle_project_scan),
    (Intent.PROJECT_INDEX, project_inspection.handle_project_index),
    (Intent.SEARCH, project_inspection.handle_search),
    (Intent.SEARCH_CODE, project_inspection.handle_search_code),
    (Intent.DEPENDENCY_MAP, project_analysis.handle_dependency_map),
    (Intent.ENTRY_POINT_QUERY, project_analysis.handle_entry_point_query),
    (Intent.DEPENDENTS_QUERY, project_analysis.handle_dependents_query),
    (Intent.DEPENDENCIES, project_analysis.handle_dependencies),
    (Intent.IMPACT_CHAIN_QUERY, project_analysis.handle_impact_chain_query),
    (Intent.CRITICALITY_QUERY, project_analysis.handle_criticality_query),
    (Intent.IMPACT_ANALYSIS, project_analysis.handle_impact_analysis),
    (Intent.FILE_IMPACT, project_analysis.handle_file_impact),
    (Intent.COMPARE_FILES, project_analysis.handle_compare_files),
    (Intent.REPORT, reports.handle_session_report),
    (Intent.SESSION_REPORT, reports.handle_session_report),
    (Intent.PROGRESS_REPORT, reports.handle_project_reports),
    (Intent.REMAINING_WORK, reports.handle_project_reports),
    (Intent.PROJECT_REPORT, reports.handle_project_reports),
    (Intent.CONTEXT_REPORT, reports.handle_context_report),
    (Intent.HISTORY, reports.handle_history),
    (Intent.WORK_STATUS, reports.handle_work_tracking),
    (Intent.REMAINING_TASKS, reports.handle_work_tracking),
    (Intent.NEXT_TASK, reports.handle_work_tracking),
    (Intent.WORK_CONTEXT, reports.handle_work_context),
    ("show_last_result", reports.handle_show_last_result),
))


def registered_intents():
    return frozenset(HANDLER_REGISTRY)


def dispatch(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    handler = HANDLER_REGISTRY.get(intent)
    if handler is None:
        return None
    if intent in {Intent.SEARCH_CODE, Intent.COMPARE_FILES, Intent.PROGRESS_REPORT, Intent.REMAINING_WORK, Intent.PROJECT_REPORT}:
        return handler(
            orchestrator, intent, target=target, raw=raw,
            authorized_ask=authorized_ask,
        )
    return handler(orchestrator, intent, target=target, raw=raw)


__all__ = ["HANDLER_REGISTRY", "build_registry", "registered_intents", "dispatch"]
