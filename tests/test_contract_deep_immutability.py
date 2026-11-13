import pytest

from lab_v4_dev.core.contracts import (
    AuditEvent,
    FrozenDict,
    FrozenList,
    PreparedExecutionRequest,
    Request,
    RouteDecision,
    RoutingDecision,
)


def test_frozen_dict_recursively_freezes_nested_mappings_and_lists():
    value = FrozenDict({"nested": {"items": ["a", {"enabled": True}]}})

    with pytest.raises(TypeError):
        value["nested"]["items"].append("b")
    with pytest.raises(TypeError):
        value["nested"]["items"][1]["enabled"] = False

    assert isinstance(value["nested"]["items"], FrozenList)
    assert value["nested"]["items"][1]["enabled"] is True


def test_route_decision_metadata_is_deeply_immutable():
    decision = RouteDecision(
        route="L-EXEC",
        evidence_scope="work_state",
        metadata={"audit": {"tags": ["route", "provider"]}},
    )

    with pytest.raises(TypeError):
        decision.metadata["audit"]["tags"].append("bypass")


def test_request_and_routing_metadata_are_deeply_immutable():
    request = Request(raw_text="hello", metadata={"source": {"labels": ["local"]}})
    routing = RoutingDecision(metadata={"route": {"candidates": ["L-FACT"]}})

    with pytest.raises(TypeError):
        request.metadata["source"]["labels"].append("remote")
    with pytest.raises(TypeError):
        routing.metadata["route"]["candidates"].append("L-EXEC")


def test_prepared_execution_and_audit_contracts_freeze_nested_data():
    prepared = PreparedExecutionRequest(
        intent="run_script",
        metadata={"execution": {"files": ["a.py"]}},
    )
    event = AuditEvent(
        timestamp="2026-11-13T00:00:00",
        event="execution",
        source="test",
        context={"scope": {"paths": ["workspace"]}},
        details={"result": {"warnings": ["none"]}},
    )

    with pytest.raises(TypeError):
        prepared.metadata["execution"]["files"].append("b.py")
    with pytest.raises(TypeError):
        event.context["scope"]["paths"].append("outside")
    with pytest.raises(TypeError):
        event.details["result"]["warnings"].append("unexpected")
