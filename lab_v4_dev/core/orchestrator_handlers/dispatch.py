"""Explicit, duplicate-safe registry for migrated Orchestrator intents."""

from types import MappingProxyType

from lab_v4_dev.intent.intents import Intent
from . import system_inspection, project_inspection, project_analysis, reports, knowledge, releases, sessions


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
    (Intent.CAPABILITIES, knowledge.handle_capabilities),
    (Intent.SAVE_KB, knowledge.handle_save_kb),
    (Intent.SKIP_KB, knowledge.handle_skip_kb),
    (Intent.CYBER_EXPLAIN, knowledge.handle_cyber_explain),
    (Intent.LAST_PROJECT, releases.handle_last_project),
    (Intent.CURRENT_VERSION, releases.handle_current_version),
    (Intent.RELEASE_INDEX, releases.handle_release_index),
    (Intent.ANALYZE_RELEASE, releases.handle_analyze_release),
    (Intent.COMPARE_VERSIONS, releases.handle_compare_versions),
    (Intent.PROJECT_TIMELINE, releases.handle_project_timeline),
    (Intent.SWITCH_PROJECT, releases.handle_switch_project),
    (Intent.RETURN_BASE_PROJECT, releases.handle_switch_project),
    (Intent.RESUME, sessions.handle_session_restore),
    (Intent.SESSION_RESTORE, sessions.handle_session_restore),
    (Intent.SESSION_SAVE, sessions.handle_session_save),
    ("show_last_result", reports.handle_show_last_result),
))


def registered_intents():
    return frozenset(HANDLER_REGISTRY)


def dispatch(orchestrator, intent, *, target=None, raw=None, authorized_ask=None, response_attributes=None, conversation_history=None, context_transition=None, route_decision=None, session_selector=None):
    handler = HANDLER_REGISTRY.get(intent)
    if handler is None:
        return None
    if intent in {Intent.RESUME, Intent.SESSION_RESTORE}:
        return handler(
            orchestrator, intent, target=target, raw=raw,
            route_decision=route_decision, session_selector=session_selector,
        )
    if intent == Intent.SESSION_SAVE:
        return handler(orchestrator, intent, target=target, raw=raw)
    if intent == Intent.CYBER_EXPLAIN:
        return handler(
            orchestrator, intent, target=target, raw=raw,
            authorized_ask=authorized_ask,
            response_attributes=response_attributes,
            conversation_history=conversation_history,
            context_transition=context_transition,
        )
    if intent in {Intent.SEARCH_CODE, Intent.COMPARE_FILES, Intent.PROGRESS_REPORT, Intent.REMAINING_WORK, Intent.PROJECT_REPORT, Intent.ANALYZE_RELEASE, Intent.COMPARE_VERSIONS}:
        return handler(
            orchestrator, intent, target=target, raw=raw,
            authorized_ask=authorized_ask,
        )
    return handler(orchestrator, intent, target=target, raw=raw)


__all__ = ["HANDLER_REGISTRY", "build_registry", "registered_intents", "dispatch"]
