from lab_v4_dev.core.contracts import (
    Request,
    Context,
    Result,
    Response,
    RoutingDecision,
)


def test_request_contract():
    r = Request.from_input("حلل orchestrator.py")
    assert r.raw_text == "حلل orchestrator.py"
    assert r.source == "user"


def test_request_mapping_contract():
    r = Request.from_input({
        "request": "اختبر المشروع",
        "request_id": "p00-1",
        "source": "test",
    })
    assert r.raw_text == "اختبر المشروع"
    assert r.request_id == "p00-1"
    assert r.source == "test"


def test_context_contract():
    class Store:
        current_subject = "orchestrator.py"
        current_version = None
        current_file = "orchestrator.py"
        current_analysis = "analysis"

    c = Context.from_store(Store())

    assert c.subject == "orchestrator.py"
    assert c.file == "orchestrator.py"
    assert c.analysis == "analysis"


def test_result_legacy_roundtrip():
    legacy = {
        "status": "success",
        "intent": "health",
        "text": "ok",
    }

    result = Result.from_legacy(legacy)

    assert result.status == "success"
    assert result.to_dict() == legacy


def test_response_legacy_roundtrip():
    legacy = {
        "status": "success",
        "intent": "health",
        "text": "ok",
    }

    response = Response.from_legacy(
        legacy,
        request_id="p00-test",
    )

    result = response.to_dict()

    assert result["status"] == "success"
    assert result["intent"] == "health"
    assert result["text"] == "ok"
    assert result["request_id"] == "p00-test"


def test_routing_decision_is_separate_contract():
    decision = RoutingDecision(
        intent="health",
        target=None,
        route="local",
        confidence=1.0,
    )

    assert decision.intent == "health"
    assert decision.route == "local"
