"""Explicit, duplicate-safe registry for migrated Orchestrator intents."""

from types import MappingProxyType

from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.core.contracts import RouteDecision
from . import system_inspection, project_inspection, project_analysis, reports, knowledge, releases, sessions, execution, code_authoring, maintenance, planning, repair, provider_fallback


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
    (Intent.SELF_DIAGNOSE, system_inspection.handle_diagnostics),
    (Intent.FULL_DIAGNOSE, system_inspection.handle_diagnostics),
    (Intent.CLEAN_DEVICE, maintenance.handle_clean_device),
    (Intent.DELETE_FILE, maintenance.handle_delete_file),
    (Intent.MODIFY_CODE, code_authoring.handle_modify_code),
    (Intent.RUN_SCRIPT, execution.handle_run_script),
    (Intent.REPAIR_ANALYZE, repair.handle_repair_analyze),
    (Intent.REPAIR_APPROVE, repair.handle_repair_approve),
    (Intent.READ_FILE, project_inspection.handle_read_file),
    (Intent.PROJECT_SCAN, project_inspection.handle_project_scan),
    (Intent.PROJECT_INDEX, project_inspection.handle_project_index),
    (Intent.SEARCH, project_inspection.handle_search),
    (Intent.SEARCH_CODE, project_inspection.handle_search_code),
    (Intent.READ_EXTERNAL_PROJECT, project_inspection.handle_read_external_project),
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
    (Intent.DIAGNOSE, provider_fallback.handle_provider_intent),
    (Intent.PROPOSE_SOLUTION, provider_fallback.handle_provider_intent),
    (Intent.PROPOSE_FIX, provider_fallback.handle_provider_intent),
    (Intent.RISK_ANALYSIS, provider_fallback.handle_provider_intent),
    (Intent.PLAN, provider_fallback.handle_provider_intent),
    (Intent.DECOMPOSE, provider_fallback.handle_provider_intent),
    (Intent.REFACTOR_FILE, provider_fallback.handle_provider_intent),
    (Intent.OPTIMIZE_CODE, provider_fallback.handle_provider_intent),
    (Intent.GENERATE_TEST, provider_fallback.handle_provider_intent),
    (Intent.PROJECT_PURPOSE, provider_fallback.handle_provider_intent),
    (Intent.ARCHITECTURE, provider_fallback.handle_provider_intent),
    (Intent.MODULES, provider_fallback.handle_provider_intent),
    (Intent.EXECUTION_FLOW, provider_fallback.handle_provider_intent),
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
    (Intent.LIST_SCRIPTS, execution.handle_list_scripts),
    (Intent.ERROR_REPORT, execution.handle_error_report),
    (Intent.DRY_RUN, execution.handle_dry_run),
    (Intent.RUN_HISTORY, execution.handle_run_history),
    (Intent.ANALYZE_CODE, code_authoring.handle_analyze_code),
    (Intent.GENERATE_CODE, code_authoring.handle_generate_code),
    (Intent.SHOW_CHANGES, reports.handle_show_changes),
    (Intent.CLEAN, maintenance.handle_clean),
    (Intent.CLEANUP_CODE, planning.handle_cleanup_code),
    (Intent.PLAN_CHANGE, planning.handle_plan_change),
    (Intent.REPAIR_REJECT, repair.handle_repair_reject),
    (Intent.PENDING_FIXES, repair.handle_pending_fixes),
    ("show_last_result", reports.handle_show_last_result),
))


def registered_intents():
    return frozenset(HANDLER_REGISTRY)


def dispatch(orchestrator, intent, *, target=None, raw=None, authorized_ask=None, response_attributes=None, conversation_history=None, context_transition=None, route_decision=None, session_selector=None):
    handler = HANDLER_REGISTRY.get(intent)
    if handler is None:
        return None

    from .context import HandlerContext, build_handler_facade
    handler_context = HandlerContext(
        intent=intent,
        target=target,
        raw=raw,
        route_decision=route_decision,
        session_selector=dict(session_selector or {}),
        response_attributes=dict(response_attributes or {}),
        conversation_history=list(conversation_history or []),
        context_transition=context_transition,
        authorized_provider=authorized_ask,
    )
    handler_orchestrator = build_handler_facade(orchestrator, handler_context)
    if intent in {Intent.DIAGNOSE, Intent.PROPOSE_SOLUTION, Intent.PROPOSE_FIX, Intent.RISK_ANALYSIS, Intent.PLAN, Intent.DECOMPOSE, Intent.REFACTOR_FILE, Intent.OPTIMIZE_CODE, Intent.GENERATE_TEST, Intent.PROJECT_PURPOSE, Intent.ARCHITECTURE, Intent.MODULES, Intent.EXECUTION_FLOW}:
        return handler(
            handler_orchestrator, intent, target=target, raw=raw,
            authorized_ask=authorized_ask,
        )

    if intent in {Intent.RESUME, Intent.SESSION_RESTORE}:
        return handler(
            handler_orchestrator, intent, target=target, raw=raw,
            route_decision=route_decision, session_selector=session_selector,
            authorized_ask=authorized_ask,
        )
    if intent == Intent.SESSION_SAVE:
        return handler(handler_orchestrator, intent, target=target, raw=raw)
    if intent == Intent.CYBER_EXPLAIN:
        return handler(
            handler_orchestrator, intent, target=target, raw=raw,
            authorized_ask=authorized_ask,
            response_attributes=response_attributes,
            conversation_history=conversation_history,
            context_transition=context_transition,
        )
    if intent in {Intent.SEARCH_CODE, Intent.COMPARE_FILES, Intent.PROGRESS_REPORT, Intent.REMAINING_WORK, Intent.PROJECT_REPORT, Intent.ANALYZE_RELEASE, Intent.COMPARE_VERSIONS, Intent.ANALYZE_CODE, Intent.GENERATE_CODE, Intent.MODIFY_CODE, Intent.REPAIR_ANALYZE, Intent.SELF_DIAGNOSE, Intent.FULL_DIAGNOSE}:
        return handler(
            handler_orchestrator, intent, target=target, raw=raw,
            authorized_ask=authorized_ask,
        )
    return handler(handler_orchestrator, intent, target=target, raw=raw)


__all__ = ["HANDLER_REGISTRY", "build_registry", "registered_intents", "dispatch", "route_request"]


def route_request(
    orchestrator,
    intent,
    target,
    raw,
    *,
    response_attributes: dict | None = None,
    conversation_history: list | None = None,
    context_transition: str | None = None,
    session_selector: dict | None = None,
    route_decision=None,
    ask_provider=None,
) -> dict:
    if not isinstance(route_decision, RouteDecision):
        return {
            "status": "denied", "intent": intent,
            "source": "route_decision_required_at_dispatch",
            "executed": False,
            "text": "لا يمكن اختيار مالك تنفيذ دون قرار توجيه نهائي صالح.",
        }
    if route_decision.route == "CLARIFY":
        return {
            "status": "needs_clarification",
            "intent": intent,
            "source": "route_clarification",
            "executed": False,
            "route_decision": route_decision,
            "text": "يلزم تحديد السياق أو الجلسة المقصودة قبل المتابعة.",
        }

    intent_value = str(getattr(intent, "value", intent) or "").casefold()
    authorized_intent = str(
        getattr(route_decision.intent, "value", route_decision.intent) or ""
    ).casefold()
    if intent_value != authorized_intent:
        return {
            "status": "denied", "intent": intent,
            "source": "route_decision_intent_mismatch",
            "executed": False,
            "text": "النية المطلوب تنفيذها لا تطابق النية التي أجازها قرار التوجيه.",
        }
    if route_decision.route not in {"L-EXEC", "L-SESSION", "P-TOOL"}:
        return {
            "status": "denied", "intent": intent,
            "source": "route_decision_owner_mismatch",
            "executed": False,
            "text": "هذا المسار لا يملك صلاحية استدعاء معالجات Orchestrator.",
        }

    # Dispatch is also a public ownership boundary: callers must not be able
    # to bypass the evidence-scope checks enforced by Orchestrator.handle.
    evidence_scope = str(route_decision.evidence_scope or "none")
    if route_decision.route == "L-EXEC" and evidence_scope != "work_state":
        return {
            "status": "denied", "intent": intent,
            "source": "route_decision_work_evidence_guard",
            "executed": False,
            "text": "مسار التنفيذ لا يملك نطاق الأدلة المطلوب لحالة العمل.",
        }
    if route_decision.route == "L-SESSION" and evidence_scope not in {
        "none", "saved_session", "saved_sessions",
    }:
        return {
            "status": "denied", "intent": intent,
            "source": "route_decision_session_evidence_guard",
            "executed": False,
            "text": "مسار الجلسات لا يسمح بقراءة أدلة خارج نطاق الجلسات المحفوظة.",
        }
    if route_decision.route in {"L-EXEC", "P-TOOL"} and evidence_scope in {
        "saved_session", "saved_sessions", "live_exchanges",
    }:
        return {
            "status": "denied", "intent": intent,
            "source": "route_decision_cross_scope_guard",
            "executed": False,
            "text": "لا يمكن توسيع نطاق الأدلة خارج المجال الذي أجازه قرار التوجيه.",
        }
    if route_decision.route == "P-TOOL" and evidence_scope != "none":
        return {
            "status": "denied", "intent": intent,
            "source": "route_decision_provider_evidence_guard",
            "executed": False,
            "text": "مسار المزود لا يملك نطاق أدلة محلية؛ استخدم مالك الأدلة المحلي المناسب.",
        }
    selector_kind = str((session_selector or {}).get("kind") or "none")
    if route_decision.route == "L-SESSION" and route_decision.output_kind in {
        "summary", "brief", "report", "topic_summary", "transcript",
        "continue_topic", "session_number", "session_identity",
    }:
        valid_scope = (
            evidence_scope == "saved_session"
            and route_decision.session_ref is not None
        ) or (
            evidence_scope == "saved_sessions"
            and selector_kind == "list"
            and route_decision.session_ref is None
        )
        if not valid_scope:
            return {
                "status": "denied", "intent": intent,
                "source": "route_decision_evidence_scope_guard",
                "executed": False,
                "text": "قرار التوجيه لا يحدد نطاق أدلة محفوظًا صالحًا لهذا المخرج.",
            }
    reusable_skills = []
    if (
        route_decision.route == "L-EXEC"
        and bool(route_decision.provider_allowed)
    ):
        memory = getattr(getattr(orchestrator, "agent", None), "memory", None)
        search_reusable_skills = getattr(
            memory, "search_relevant_skills", None
        )
        if callable(search_reusable_skills):
            try:
                skill_query = " ".join(
                    str(value or "")
                    for value in (intent_value, target, raw)
                ).strip()
                reusable_skills = search_reusable_skills(
                    skill_query, limit=3
                ) or []
            except Exception:
                reusable_skills = []

    def authorized_ask(*args, **kwargs):
        if route_decision is None or not bool(
            getattr(route_decision, "provider_allowed", False)
        ):
            return {
                "status": "unavailable",
                "message": "provider permission missing or denied by RouteDecision",
            }
        if not callable(ask_provider):
            return {
                "status": "unavailable",
                "message": "provider gateway capability unavailable",
            }
        if reusable_skills:
            skill_lines = [
                "Verified reusable procedures from prior successful runs:",
                "Treat these as advisory reference only. Check their preconditions,",
                "do not expand the user's requested scope, and never claim a step",
                "was executed unless the current handler actually executed it.",
            ]
            for skill in reusable_skills:
                skill_lines.append(
                    f"Skill {skill.get('id')}: {skill.get('name') or 'unnamed'}"
                )
                if skill.get("description"):
                    skill_lines.append(f"Description: {skill['description']}")
                for precondition in skill.get("preconditions") or []:
                    skill_lines.append(f"Precondition: {precondition}")
                for step_index, step in enumerate(skill.get("steps") or [], 1):
                    skill_lines.append(f"Step {step_index}: {step}")
            existing_system = str(kwargs.get("system") or "")
            kwargs["system"] = (
                existing_system + "\n\n" + "\n".join(skill_lines)
            ).strip()
        kwargs.setdefault("provider_allowed", True)
        return ask_provider(*args, **kwargs)

    # ─── Response Cache ───
    from lab_v4_dev.intent.response_cache import get as rcache_get
    _cache_intents = ["analyze_code","project_scan","cyber_explain","health","self_diagnose"]
    if intent in _cache_intents and not response_attributes:
        # لا نستخدم cache عندما يتطلب الشرح/التحليل موضوعًا ولا يوجد target.
        # يمنع إعادة إجابة قديمة عن موضوع لم يحدده المستخدم.
        _skip_cache = (
            intent in {"analyze_code", "cyber_explain"}
            and not target
        )
        if not _skip_cache:
            cached = rcache_get(str(intent), target or "")
            if cached:
                return {"status":"success","intent":intent,"source":"cache","text":cached}

    # Registered handlers run only after the response-cache gate.
    _handled = dispatch(
        orchestrator, intent, target=target, raw=raw, authorized_ask=authorized_ask,
        route_decision=route_decision, session_selector=session_selector,
        response_attributes=response_attributes,
        conversation_history=conversation_history,
        context_transition=context_transition,
    )
    if _handled is not None:
        if isinstance(_handled, dict) and reusable_skills:
            _handled.setdefault(
                "reusable_skill_candidates",
                [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "success_count": item.get("success_count", 0),
                        "failure_count": item.get("failure_count", 0),
                    }
                    for item in reusable_skills
                ],
            )
        return _handled

    # Every supported intent, including provider-backed work, is owned
    # by HANDLER_REGISTRY. No secondary provider-selection branch exists.
    return {
        "status": "unsupported",
        "intent": intent,
        "message": f"لم أفهم الأمر: {raw[:50]}",
        "executed": False,
    }
