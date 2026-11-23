from pathlib import Path

from lab_v4_dev.core.orchestrator_handlers.dispatch import HANDLER_REGISTRY
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.llm.router import needs_llm


def test_intent_route_matrix_covers_every_declared_intent_value():
    root = Path(__file__).resolve().parents[1]
    matrix = (root / "docs" / "orchestrator" / "INTENT_ROUTE_AUTHORIZATION_MATRIX.md").read_text(encoding="utf-8")

    declared = {
        value for name, value in vars(Intent).items()
        if name.isupper() and isinstance(value, str)
    }
    inventory_section = matrix.split("## Per-intent inventory", 1)[1].split("## Interpretation notes", 1)[0]
    rows = {
        line.split("`", 2)[1]
        for line in inventory_section.splitlines()
        if line.startswith("| `")
    }

    assert len(declared) == 166
    assert rows == declared
    assert len(HANDLER_REGISTRY) == 69
    assert "show_last_result" in HANDLER_REGISTRY
    llm_intents = {intent for intent in declared if needs_llm(intent)}
    assert len(llm_intents) == 19
    assert len(llm_intents - set(HANDLER_REGISTRY)) == 13
