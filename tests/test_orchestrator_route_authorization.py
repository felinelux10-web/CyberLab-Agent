from types import SimpleNamespace

from lab_v4_dev.core.contracts import RouteDecision
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.core.task_chain import execute_chain
from lab_v4_dev.intent.intents import Intent


def test_orchestrator_handle_denies_missing_route_decision():
    orchestrator = object.__new__(Orchestrator)

    result = orchestrator.handle("status", parsed={"intent": Intent.STATUS})

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_required"
    assert result["executed"] is False


def test_orchestrator_handle_rejects_intent_mismatch():
    orchestrator = object.__new__(Orchestrator)
    decision = RouteDecision(route="L-EXEC", intent=Intent.STATUS)

    result = orchestrator.handle(
        "health",
        parsed={"intent": Intent.HEALTH},
        route_decision=decision,
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_intent_mismatch"
    assert result["executed"] is False


def test_task_chain_routes_each_child_through_conversation_manager():
    calls = []
    parent = SimpleNamespace(route="L-EXEC", provider_allowed=False)

    class Manager:
        def process_execution_step(self, step, *, parsed, parent_route_decision):
            calls.append((step, parsed, parent_route_decision))
            return {"status": "success", "text": "completed"}

    class OrchestratorStub:
        context = SimpleNamespace(
            current_analysis=None,
            current_file=None,
            current_subject=None,
            last_result=None,
        )
        agent = SimpleNamespace(conv_manager=Manager())

        def handle(self, *_args, **_kwargs):
            raise AssertionError("TaskChain must not call the raw Orchestrator facade")

    result = execute_chain(["status"], OrchestratorStub(), parent_route_decision=parent)

    assert result["status"] == "success"
    assert result["steps"] == 1
    assert len(calls) == 1
    assert calls[0][2] is parent


def test_task_chain_propagates_child_failure_and_stops():
    calls = []

    class Manager:
        def process_execution_step(self, step, *, parsed, parent_route_decision):
            calls.append(step)
            return {"status": "denied", "text": "child route denied"}

    class OrchestratorStub:
        context = SimpleNamespace(
            current_analysis=None,
            current_file=None,
            current_subject=None,
            last_result=None,
        )
        agent = SimpleNamespace(conv_manager=Manager())

    parent = SimpleNamespace(route="L-EXEC", provider_allowed=False)
    result = execute_chain(["status", "health"], OrchestratorStub(), parent_route_decision=parent)

    assert result["status"] == "failed"
    assert result["executed"] is False
    assert result["failed_step"] == 1
    assert len(calls) == 1


def test_orchestrator_rejects_execution_with_wrong_evidence_scope():
    orchestrator = object.__new__(Orchestrator)
    decision = RouteDecision(
        route="L-EXEC", evidence_scope="saved_session", intent=Intent.STATUS
    )

    result = orchestrator.handle(
        "status", parsed={"intent": Intent.STATUS}, route_decision=decision
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_work_evidence_guard"


def test_orchestrator_rejects_saved_session_scope_on_project_route():
    orchestrator = object.__new__(Orchestrator)
    decision = RouteDecision(
        route="L-FACT", evidence_scope="saved_sessions", intent=Intent.AGENT_CAPABILITIES
    )

    result = orchestrator.handle(
        "capabilities", parsed={"intent": Intent.AGENT_CAPABILITIES},
        route_decision=decision,
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_project_evidence_guard"
