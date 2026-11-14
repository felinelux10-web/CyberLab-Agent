from types import SimpleNamespace

import pytest

from lab_v4_dev.core.contracts import PreparedExecutionRequest, RouteDecision
from lab_v4_dev.core.orchestrator import Orchestrator


def _decision(*, route="L-EXEC", evidence_scope="work_state", intent="run_command"):
    return RouteDecision(
        route=route,
        evidence_scope=evidence_scope,
        intent=intent,
        provider_allowed=False,
    )


@pytest.mark.parametrize(
    "decision, message",
    [
        (_decision(route="L-SOCIAL"), "L-EXEC work_state"),
        (_decision(evidence_scope="project_state"), "L-EXEC work_state"),
        (_decision(intent="delete_file"), "does not match RouteDecision"),
    ],
)
def test_prepared_execution_contract_rejects_invalid_route_scope_or_intent(decision, message):
    with pytest.raises(ValueError, match=message):
        PreparedExecutionRequest(
            intent="run_command",
            route_decision=decision,
            metadata={"execution": {"action": "run_command", "parameters": {}}},
        )


def test_prepared_execution_contract_requires_real_route_decision():
    with pytest.raises(TypeError, match="route_decision must be a RouteDecision"):
        PreparedExecutionRequest(
            intent="run_command",
            route_decision=SimpleNamespace(
                route="L-EXEC",
                evidence_scope="work_state",
                intent="run_command",
            ),
        )


def test_orchestrator_prepared_handoff_denies_missing_route_before_queueing():
    calls = []

    class FakeLoop:
        def submit_prepared(self, request):
            calls.append(request)

        def tick(self):
            return {"status": "executed"}

    orchestrator = object.__new__(Orchestrator)
    orchestrator.agent = SimpleNamespace(loop=FakeLoop())

    result = orchestrator._submit_prepared_execution(
        "run_command",
        execution={"action": "run_command", "parameters": {"command": "echo blocked"}},
    )

    assert result["status"] == "denied"
    assert result["source"] == "prepared_execution_route_guard"
    assert calls == []


def test_orchestrator_prepared_handoff_passes_authorized_typed_request():
    calls = []

    class FakeLoop:
        def submit_prepared(self, request):
            calls.append(request)

        def tick(self):
            return {"status": "executed", "executed": True}

    orchestrator = object.__new__(Orchestrator)
    orchestrator.agent = SimpleNamespace(loop=FakeLoop())
    decision = _decision()

    result = orchestrator._submit_prepared_execution(
        "run_command",
        target="shell",
        request_id="prepared-authorized-01",
        execution={"action": "run_command", "parameters": {"command": "echo authorized"}},
        route_decision=decision,
    )

    assert result == {"status": "executed", "executed": True}
    assert len(calls) == 1
    assert isinstance(calls[0], PreparedExecutionRequest)
    assert calls[0].route_decision is decision
    assert calls[0].intent == "run_command"
    assert calls[0].metadata["execution"]["action"] == "run_command"
