import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "lab_v4_dev"
AUTHORIZED_GATEWAY_MODULES = {
    "conversation/conversation_manager.py",
    "core/orchestrator.py",
    "intent/llm_intent_resolver.py",
    "llm/smart_router.py",
}


def test_gateway_imports_are_confined_to_audited_policy_boundaries():
    imported_modules = set()
    violations = []

    for path in ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path.relative_to(ROOT)}: syntax error: {exc}")
            continue

        aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "lab_v4_dev.llm.gateway":
                for item in node.names:
                    if item.name == "ask":
                        aliases.add(item.asname or item.name)

        if not aliases:
            continue

        relative = path.relative_to(ROOT).as_posix()
        imported_modules.add(relative)
        if relative not in AUTHORIZED_GATEWAY_MODULES:
            violations.append(f"{relative}: direct gateway import outside audited boundary")
            continue

        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in aliases
        ]
        if not calls:
            violations.append(f"{relative}: gateway import has no visible authorized call")
            continue

        if relative == "conversation/conversation_manager.py":
            if any(
                not any(keyword.arg == "provider_allowed" for keyword in call.keywords)
                for call in calls
            ):
                violations.append(f"{relative}: call missing explicit provider grant")
            if "route_decision is not None and bool(" not in source:
                violations.append(f"{relative}: route decision is not required before provider use")
        elif relative == "intent/llm_intent_resolver.py":
            if "provider_allowed: bool = False" not in source or "if not provider_allowed:" not in source:
                violations.append(f"{relative}: pre-route NLU grant must default to deny")
            if any(
                not any(keyword.arg == "provider_allowed" for keyword in call.keywords)
                for call in calls
            ):
                violations.append(f"{relative}: NLU gateway call missing explicit grant")
        elif relative == "llm/smart_router.py":
            if "provider_allowed: bool = False" not in source or "if not provider_allowed:" not in source:
                violations.append(f"{relative}: compatibility router must default to deny")
            if any(
                not any(keyword.arg == "provider_allowed" for keyword in call.keywords)
                for call in calls
            ):
                violations.append(f"{relative}: gateway call missing explicit grant")
        elif relative == "core/orchestrator.py":
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
