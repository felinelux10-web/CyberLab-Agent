import ast
from pathlib import Path


def test_authoritative_orchestrator_caller_graph_is_explicit():
    root = Path(__file__).resolve().parents[1]
    source_root = root / "lab_v4_dev"

    orchestrator_handle = []
    legacy_route = []
    prepared_submit = []
    raw_loop_submit = []
    prepared_helper_calls = []
    child_step_calls = []
    agent_conversation_calls = []

    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            value = node.func.value
            if node.func.attr == "handle" and isinstance(value, ast.Attribute) and value.attr == "orchestrator":
                orchestrator_handle.append(relative)
            if node.func.attr == "_route" and isinstance(value, ast.Attribute) and value.attr == "orchestrator":
                legacy_route.append(relative)
            if node.func.attr == "submit_prepared":
                prepared_submit.append(relative)
            if node.func.attr == "submit" and isinstance(value, ast.Attribute) and value.attr == "loop":
                raw_loop_submit.append(relative)
            if node.func.attr == "_submit_prepared_execution":
                prepared_helper_calls.append(relative)
            if node.func.attr == "process_execution_step":
                child_step_calls.append(relative)
            if node.func.attr == "process" and isinstance(value, ast.Attribute) and value.attr == "conv_manager":
                agent_conversation_calls.append(relative)

    assert orchestrator_handle == ["conversation/conversation_manager.py"]
    assert legacy_route == []
    assert prepared_submit == ["core/orchestrator.py"]
    assert raw_loop_submit == []
    assert prepared_helper_calls == []
    assert child_step_calls == ["core/task_chain.py"]
    assert agent_conversation_calls == ["core/agent.py"]

    guard = (source_root / "core" / "guard.py").read_text(encoding="utf-8")
    task_chain = (source_root / "core" / "task_chain.py").read_text(encoding="utf-8")
    assert "lab_v4_dev.llm.gateway" not in guard
    assert "orchestrator.handle(" not in guard
    assert "manager.process_execution_step(" in task_chain
    assert "orchestrator.handle(" not in task_chain
