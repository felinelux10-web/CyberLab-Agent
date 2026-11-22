from types import SimpleNamespace

from lab_v4_dev.core.contracts import RouteDecision, SessionRef
from lab_v4_dev.core.orchestrator_handlers.dispatch import route_request
from lab_v4_dev.intent.intents import Intent


def _orchestrator():
    return SimpleNamespace(
        services=SimpleNamespace(),
        agent=SimpleNamespace(),
    )


def test_dispatch_rejects_provider_route_with_saved_session_evidence():
    decision = RouteDecision(
        route="P-TOOL",
        session_scope="saved_id",
        session_ref=SessionRef(session_id="saved-1"),
        intent=Intent.CYBER_EXPLAIN,
        evidence_scope="saved_session",
        provider_allowed=True,
    )
    provider_calls = []

    result = route_request(
        _orchestrator(),
        Intent.CYBER_EXPLAIN,
        "موضوع",
        "اشرح الموضوع",
        route_decision=decision,
        ask_provider=lambda *args, **kwargs: provider_calls.append(args),
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_cross_scope_guard"
    assert provider_calls == []


def test_dispatch_rejects_execution_route_without_work_state_evidence():
    decision = RouteDecision(
        route="L-EXEC",
        intent=Intent.CLEAN,
        evidence_scope="none",
        provider_allowed=False,
    )

    result = route_request(
        _orchestrator(),
        Intent.CLEAN,
        "",
        "نظف",
        route_decision=decision,
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_work_evidence_guard"


def test_dispatch_rejects_saved_report_without_exact_session_identity():
    decision = RouteDecision(
        route="L-SESSION",
        output_kind="report",
        evidence_scope="saved_sessions",
        provider_allowed=False,
        intent=Intent.SESSION_RESTORE,
    )

    result = route_request(
        _orchestrator(),
        Intent.SESSION_RESTORE,
        "",
        "اكتب تقريرًا",
        route_decision=decision,
        session_selector={"kind": "number", "number": 72},
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_evidence_scope_guard"

def test_dispatch_rejects_provider_route_with_project_state_evidence():
    decision = RouteDecision(
        route="P-TOOL",
        intent=Intent.CYBER_EXPLAIN,
        evidence_scope="project_state",
        provider_allowed=True,
    )

    result = route_request(
        _orchestrator(),
        Intent.CYBER_EXPLAIN,
        "موضوع",
        "اشرح الموضوع",
        route_decision=decision,
        ask_provider=lambda *_args, **_kwargs: {
            "status": "success", "text": "يجب ألا يصل التنفيذ إلى المزود."
        },
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_provider_evidence_guard"

