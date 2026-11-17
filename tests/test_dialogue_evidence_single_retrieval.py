import ast
from pathlib import Path

from lab_v4_dev.memory import dialogue_knowledge as knowledge


def test_recall_handler_retrieves_evidence_once_and_passes_it():
    source_path = (
        Path(__file__).resolve().parents[1]
        / "lab_v4_dev"
        / "core"
        / "orchestrator_handlers"
        / "sessions.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    handler = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "handle_session_restore":
                handler = node
                break

    assert handler is not None, "handle_session_restore was not found"

    retrieval_calls = []
    formatter_calls = []

    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue

        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
        )

        if name == "retrieve_dialogue_evidence":
            retrieval_calls.append(node)

        if name == "format_dialogue_evidence_answer":
            formatter_calls.append(node)

    assert len(retrieval_calls) == 1, (
        "The session restore handler must retrieve evidence only once"
    )
    assert len(formatter_calls) >= 1, (
        "The session restore handler must call the evidence formatter"
    )

    passed_evidence = any(
        keyword.arg == "evidence"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "evidence"
        for call in formatter_calls
        for keyword in call.keywords
    )

    assert passed_evidence, (
        "The formatter must receive the already retrieved evidence variable"
    )


def test_formatter_uses_supplied_evidence_without_retrieving(monkeypatch):
    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError(
            "Retrieval must not run when evidence is supplied"
        )

    monkeypatch.setattr(
        knowledge,
        "retrieve_dialogue_evidence",
        unexpected_retrieval,
    )

    result = knowledge.format_dialogue_evidence_answer(
        {},
        "test query",
        evidence=[],
    )

    assert isinstance(result, str)


def test_formatter_without_supplied_evidence_keeps_legacy_retrieval(
    monkeypatch,
):
    calls = []
    supplied = []

    def fake_retrieval(data, query, *, limit=8):
        calls.append((data, query, limit))
        return supplied

    monkeypatch.setattr(
        knowledge,
        "retrieve_dialogue_evidence",
        fake_retrieval,
    )

    data = {}
    query = "legacy retrieval test"

    expected = knowledge.format_dialogue_evidence_answer(
        data,
        query,
        evidence=supplied,
    )

    calls.clear()

    actual = knowledge.format_dialogue_evidence_answer(
        data,
        query,
    )

    assert len(calls) == 1
    assert calls[0] == (data, query, 8)
    assert actual == expected
