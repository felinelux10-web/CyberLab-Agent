import ast
from pathlib import Path


def _python_files(root):
    # workspace/ contains user-generated scripts and snippets, not application source.
    # These directories are local/generated or archived snapshots, not active runtime source.
    ignored = {
        ".git", ".venv", "venv", "__pycache__", "build", "dist", ".tox",
        "workspace", "stable", "releases", "_archived_orphans_20260621",
    }
    for path in root.rglob("*.py"):
        if any(part in ignored for part in path.parts):
            continue
        yield path


def _receiver_has_attr(node, name):
    return isinstance(node, ast.Attribute) and node.attr == name


def test_repository_wide_runtime_caller_graph_and_dynamic_boundaries():
    root = Path(__file__).resolve().parents[1]
    active_calls = {
        "orchestrator_handle": [],
        "orchestrator_route": [],
        "prepared_submit": [],
        "raw_loop_submit": [],
        "prepared_helper_calls": [],
        "child_step_calls": [],
        "agent_conversation_calls": [],
        "prepared_request_constructors": [],
        "dynamic_manager_process": [],
        "legacy_imports": [],
    }

    for path in _python_files(root):
        relative = path.relative_to(root).as_posix()
        parts = set(path.relative_to(root).parts)
        if "tests" in parts:
            continue
        if "lab_v4" in parts and "lab_v4_dev" not in parts:
            # Retained legacy tree: inventory it separately, but it is not the active runtime.
            continue

        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("lab_v4."):
                active_calls["legacy_imports"].append(relative)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("lab_v4."):
                        active_calls["legacy_imports"].append(relative)

            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                receiver = func.value
                if func.attr == "handle" and _receiver_has_attr(receiver, "orchestrator"):
                    active_calls["orchestrator_handle"].append(relative)
                if func.attr == "_route" and _receiver_has_attr(receiver, "orchestrator"):
                    active_calls["orchestrator_route"].append(relative)
                if func.attr == "submit_prepared":
                    active_calls["prepared_submit"].append(relative)
                if func.attr == "submit" and _receiver_has_attr(receiver, "loop"):
                    active_calls["raw_loop_submit"].append(relative)
                if func.attr == "_submit_prepared_execution":
                    active_calls["prepared_helper_calls"].append(relative)
                if func.attr == "process_execution_step":
                    active_calls["child_step_calls"].append(relative)
                if func.attr == "process" and _receiver_has_attr(receiver, "conv_manager"):
                    active_calls["agent_conversation_calls"].append(relative)
                if func.attr == "PreparedExecutionRequest":
                    active_calls["prepared_request_constructors"].append(relative)
            if isinstance(func, ast.Name) and func.id == "PreparedExecutionRequest":
                active_calls["prepared_request_constructors"].append(relative)
            if (
                isinstance(func, ast.Name)
                and func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "manager"
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "process"
            ):
                active_calls["dynamic_manager_process"].append(relative)

    assert active_calls["orchestrator_handle"] == [
        "lab_v4_dev/conversation/conversation_manager.py"
    ]
    assert active_calls["orchestrator_route"] == []
    assert active_calls["prepared_submit"] == ["lab_v4_dev/core/orchestrator.py"]
    assert active_calls["raw_loop_submit"] == []
    assert active_calls["prepared_helper_calls"] == []
    assert active_calls["child_step_calls"] == ["lab_v4_dev/core/task_chain.py"]
    assert active_calls["agent_conversation_calls"] == ["lab_v4_dev/core/agent.py"]
    assert active_calls["prepared_request_constructors"] == ["lab_v4_dev/core/orchestrator.py"]
    assert active_calls["dynamic_manager_process"] == ["lab_v4_dev/core/guard.py"]
    assert active_calls["legacy_imports"] == []

    guard = (root / "lab_v4_dev" / "core" / "guard.py").read_text(encoding="utf-8")
    task_chain = (root / "lab_v4_dev" / "core" / "task_chain.py").read_text(encoding="utf-8")
    agent = (root / "lab_v4_dev" / "core" / "agent.py").read_text(encoding="utf-8")
    assert "lab_v4_dev.llm.gateway" not in guard
    assert "orchestrator.handle(" not in guard
    assert "manager.process_execution_step(" in task_chain
    assert "orchestrator.handle(" not in task_chain
    assert "self.conv_manager.process(" in agent

    services = (root / "lab_v4_dev" / "core" / "orchestrator_handlers" / "services.py").read_text(encoding="utf-8")
    execution = (root / "lab_v4_dev" / "core" / "orchestrator_handlers" / "execution.py").read_text(encoding="utf-8")
    assert 'if intent == Intent.RUN_SCRIPT:' in services
    assert 'fields.add("submit_prepared_execution")' in services
    assert 'getattr(orchestrator, "_submit_prepared_execution", None)' in services
    assert 'submit_prepared(' in execution
    assert 'route_decision=route_decision' in execution
    assert 'run_code(' not in execution[execution.index("def handle_run_script("):]
