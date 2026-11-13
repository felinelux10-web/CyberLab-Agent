from types import SimpleNamespace

from lab_v4_dev.core.guard import execute, guard
from lab_v4_dev.intent.intents import Intent


def test_guard_never_selects_an_external_provider():
    result = guard({
        "intent": Intent.PROJECT_SCAN,
        "raw": "افحص المشروع",
        "context": "project_level",
    })

    assert result["route"] == "conversation_manager"
    assert result["intent"] == Intent.PROJECT_SCAN


def test_guard_clarification_remains_local():
    result = guard({"intent": Intent.UNCLEAR, "raw": "..."})

    assert result["route"] == "clarify"


def test_guard_execute_requires_conversation_manager_and_never_uses_legacy_orchestrator():
    class ForbiddenOrchestrator:
        def handle(self, *_args, **_kwargs):
            raise AssertionError("Guard must not call Orchestrator directly")

    agent = SimpleNamespace(conv_manager=None, orchestrator=ForbiddenOrchestrator())
    result = execute({"route": "conversation_manager", "raw": "افحص المشروع"}, agent)

    assert result["status"] == "denied"
    assert result["source"] == "guard_route_required"


def test_guard_execute_delegates_to_conversation_manager():
    calls = []
    manager = SimpleNamespace(process=lambda raw: calls.append(raw) or {"status": "success"})
    agent = SimpleNamespace(conv_manager=manager)

    result = execute({"route": "conversation_manager", "raw": "افحص المشروع"}, agent)

    assert calls == ["افحص المشروع"]
    assert result["status"] == "success"
