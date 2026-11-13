import pytest

from lab_v4_dev.core.orchestrator_handlers.context import HandlerContext, FrozenList


def test_handler_context_recursively_freezes_nested_request_data():
    context = HandlerContext(
        intent="report",
        session_selector={"selection": {"number": 72}},
        response_attributes={"flags": ["summary", {"strict": True}]},
        conversation_history=[
            {"role": "user", "metadata": {"tags": ["project", "dialogue"]}}
        ],
    )

    with pytest.raises(TypeError):
        context.session_selector["selection"]["number"] = 73
    with pytest.raises(TypeError):
        context.response_attributes["flags"].append("report")
    with pytest.raises(TypeError):
        context.conversation_history[0]["metadata"]["tags"].append("work")

    assert isinstance(context.conversation_history, FrozenList)
    assert context.session_selector["selection"]["number"] == 72
    assert context.response_attributes["flags"][0] == "summary"
    assert context.conversation_history[0]["metadata"]["tags"] == ["project", "dialogue"]


def test_handler_context_keeps_read_only_dict_and_list_compatibility():
    context = HandlerContext(
        intent="report",
        session_selector={"kind": "id"},
        response_attributes={"output_kind": "summary"},
        conversation_history=[{"role": "user", "content": "hello"}],
    )

    assert isinstance(context.session_selector, dict)
    assert isinstance(context.response_attributes, dict)
    assert isinstance(context.conversation_history, list)
    assert context.session_selector.get("kind") == "id"
    assert context.conversation_history[0]["content"] == "hello"
