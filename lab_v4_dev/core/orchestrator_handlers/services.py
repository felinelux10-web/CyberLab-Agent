"""Explicit service capabilities exposed to handlers; never pass the Agent itself."""

from dataclasses import dataclass
from typing import Any


@dataclass
class HandlerServices:
    state: Any = None
    session: Any = None
    memory: Any = None
    dialogue_memory: Any = None
    restore_session_snapshot: Any = None
    restore_session_context: Any = None
    metadata: Any = None
    db: Any = None
    analyzed_files: Any = None
    impact_analyzed: Any = None
    pipeline_factory: Any = None


def build_handler_services(orchestrator, intent=None) -> HandlerServices:
    """Expose only the capability fields required by this handler's intent."""
    from lab_v4_dev.intent.intents import Intent

    fields = set()
    if intent in {Intent.HEALTH, Intent.SYSTEM_STATUS, Intent.STATUS}:
        fields.add("state")
    if intent in {Intent.STATUS, Intent.REPORT, Intent.SESSION_REPORT}:
        fields.add("session")
    if intent in {
        Intent.HISTORY, Intent.WORK_STATUS, Intent.REMAINING_TASKS,
        Intent.NEXT_TASK, Intent.SHOW_CHANGES, Intent.PROGRESS_REPORT,
        Intent.REMAINING_WORK, Intent.PROJECT_REPORT,
    }:
        fields.add("memory")
    if intent in {Intent.RESUME, Intent.SESSION_RESTORE, Intent.SESSION_SAVE}:
        fields.update({
            "dialogue_memory", "restore_session_snapshot",
            "restore_session_context", "metadata",
        })
    if intent in {Intent.ANALYZE_CODE, Intent.MODIFY_CODE}:
        fields.add("analyzed_files")
    if intent in {
        Intent.DEPENDENCY_MAP, Intent.ENTRY_POINT_QUERY, Intent.DEPENDENTS_QUERY,
        Intent.DEPENDENCIES, Intent.IMPACT_CHAIN_QUERY, Intent.CRITICALITY_QUERY,
        Intent.IMPACT_ANALYSIS, Intent.FILE_IMPACT, Intent.COMPARE_FILES,
        Intent.ANALYZE_CODE, Intent.MODIFY_CODE,
    }:
        fields.add("impact_analyzed")
    if intent == Intent.MODIFY_CODE:
        fields.update({"db", "pipeline_factory"})

    agent = getattr(orchestrator, "agent", None)
    values = {}
    for field_name in fields:
        if field_name == "analyzed_files":
            value = getattr(orchestrator, "_analyzed_files", None)
            if value is None:
                value = set()
                setattr(orchestrator, "_analyzed_files", value)
        elif field_name == "impact_analyzed":
            value = getattr(orchestrator, "_impact_analyzed", None)
            if value is None:
                value = set()
                setattr(orchestrator, "_impact_analyzed", value)
        elif field_name == "pipeline_factory":
            value = getattr(orchestrator, "_get_pipeline", None)
        elif field_name == "metadata":
            value = getattr(agent, "_meta", None)
        else:
            value = getattr(agent, field_name, None)
        values[field_name] = value
    return HandlerServices(**values)


__all__ = ["HandlerServices", "build_handler_services"]
