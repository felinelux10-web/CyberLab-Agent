import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "lab_v4_dev"
AUTHORIZED_GATEWAY_MODULES = {
    "lab_v4_dev/conversation/conversation_manager.py",
    "lab_v4_dev/core/orchestrator.py",
}


def test_gateway_imports_are_confined_to_repository_runtime_policy_boundaries():
    imported_modules = set()
    violations = []
    ignored = {".git", ".venv", "venv", "__pycache__", "build", "dist", ".tox"}

    for path in REPO_ROOT.rglob("*.py"):
        relative_parts = path.relative_to(REPO_ROOT).parts
        if any(part in ignored for part in relative_parts):
            continue
        if "tests" in relative_parts:
            continue
        if "lab_v4" in relative_parts and "lab_v4_dev" not in relative_parts:
            continue

        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path.relative_to(REPO_ROOT)}: syntax error: {exc}")
            continue

        aliases = set()
        dynamic_gateway_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "lab_v4_dev.llm.gateway":
                for item in node.names:
                    if item.name == "ask":
                        aliases.add(item.asname or item.name)
            elif isinstance(node, ast.ImportFrom) and node.module == "lab_v4_dev.llm":
                for item in node.names:
                    if item.name == "gateway":
                        aliases.add(item.asname or item.name)
            elif isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "import_module"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "lab_v4_dev.llm.gateway"
                ):
                    dynamic_gateway_import = True
                if (
                    isinstance(func, ast.Name)
                    and func.id == "__import__"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "lab_v4_dev.llm.gateway"
                ):
                    dynamic_gateway_import = True

        relative = path.relative_to(REPO_ROOT).as_posix()
        if dynamic_gateway_import:
            violations.append(f"{relative}: dynamic gateway import outside the static policy inventory")
        if not aliases:
            continue

        imported_modules.add(relative)
        if relative not in AUTHORIZED_GATEWAY_MODULES:
            violations.append(f"{relative}: direct gateway import outside audited boundary")
            continue

        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id in aliases)
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "ask"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in aliases
                )
            )
        ]
        if not calls:
            violations.append(f"{relative}: gateway import has no visible authorized call")
            continue

        if relative == "lab_v4_dev/conversation/conversation_manager.py":
            if any(
                not any(keyword.arg == "provider_allowed" for keyword in call.keywords)
                for call in calls
            ):
                violations.append(f"{relative}: call missing explicit provider grant")
            if "route_decision is not None and bool(" not in source:
                violations.append(f"{relative}: route decision is not required before provider use")
        elif relative == "lab_v4_dev/core/orchestrator.py":
            if 'kwargs.setdefault("provider_allowed", True)' not in source:
                violations.append(f"{relative}: provider grant is not injected by the authorized callback")
            if any(
                not any(keyword.arg is None and isinstance(keyword.value, ast.Name)
                        and keyword.value.id == "kwargs" for keyword in call.keywords)
                for call in calls
            ):
                violations.append(f"{relative}: gateway call bypasses the authorized callback kwargs")

    if imported_modules != AUTHORIZED_GATEWAY_MODULES:
        violations.append(
            "gateway import inventory mismatch: "
            f"expected={sorted(AUTHORIZED_GATEWAY_MODULES)}, "
            f"found={sorted(imported_modules)}"
        )

    assert violations == []


def test_pre_route_nlu_requires_an_injected_capability_and_has_no_gateway_import():
    resolver = (ROOT / "intent" / "llm_intent_resolver.py").read_text(encoding="utf-8")
    parser = (ROOT / "intent" / "intent_parser.py").read_text(encoding="utf-8")
    groq_compat = (ROOT / "intent" / "groq_intent_resolver.py").read_text(encoding="utf-8")
    smart_router = (ROOT / "llm" / "smart_router.py").read_text(encoding="utf-8")

    assert "lab_v4_dev.llm.gateway" not in resolver
    assert "nlu_provider=None" in resolver
    assert "if not callable(nlu_provider):" in resolver
    assert "raw = nlu_provider(prompt)" in resolver
    assert "intent     = resolve(user_input)" in parser
    assert "lab_v4_dev.llm.gateway" not in groq_compat
    assert "from lab_v4_dev.intent.llm_intent_resolver import resolve" in groq_compat

    assert "lab_v4_dev.llm.gateway" not in smart_router
    assert "authorized_ask=None" in smart_router
    assert "if not callable(authorized_ask):" in smart_router
    assert "result = authorized_ask(" in smart_router
