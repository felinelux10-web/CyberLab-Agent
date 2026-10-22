"""Guard the canonical runtime against reintroducing legacy-package imports."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _legacy_imports(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            continue
        found.extend(
            f"{source_path.relative_to(ROOT)}:{node.lineno}: {module}"
            for module in modules
            if module == "lab_v4" or module.startswith("lab_v4.")
        )
    return found


def test_entrypoint_uses_the_canonical_agent():
    source = (ROOT / "run.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="run.py")
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if node.module == "lab_v4_dev.core.agent"
    }
    assert "Agent" in imports


def test_active_runtime_does_not_import_the_legacy_package():
    active_sources = [ROOT / "run.py", *sorted((ROOT / "lab_v4_dev").rglob("*.py"))]
    violations = [
        violation
        for source_path in active_sources
        for violation in _legacy_imports(source_path)
    ]
    assert not violations, "Legacy imports found in active runtime:\n" + "\n".join(violations)
