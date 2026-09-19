from lab_v4_dev.core.contracts import Context, PreparedExecutionRequest


def test_prepared_execution_request_contract():
    request = PreparedExecutionRequest(
        intent="TEST_INTENT",
        target="TEST_TARGET",
        context=Context(),
        request_id="test-001",
        metadata={"source": "contract-test"},
    )

    assert request.intent == "TEST_INTENT"
    assert request.target == "TEST_TARGET"
    assert request.request_id == "test-001"
    assert request.metadata["source"] == "contract-test"

    assert not hasattr(request, "raw_text")
    assert not hasattr(request, "actions")
