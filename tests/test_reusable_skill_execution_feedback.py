from types import SimpleNamespace

from lab_v4_dev.core.contracts import RouteDecision
import importlib

dispatch_module = importlib.import_module(
    "lab_v4_dev.core.orchestrator_handlers.dispatch"
)
from lab_v4_dev.intent.intents import Intent


def _route(monkeypatch, handler_result, *, invoke_provider=True):
    skill_runs = []
    provider_calls = []
    skill = {
        "id": 17,
        "name": "verified-code-edit",
        "description": "Apply a narrow validated code change.",
        "steps": ["inspect target", "apply minimal patch", "verify written result"],
        "preconditions": ["target file is authorized"],
        "success_count": 2,
        "failure_count": 0,
    }
    memory = SimpleNamespace(
        search_relevant_skills=lambda query, limit: [skill],
        record_skill_run=lambda skill_id, **result: skill_runs.append(
            (skill_id, result)
        ),
    )
    orchestrator = SimpleNamespace(agent=SimpleNamespace(memory=memory))
    decision = RouteDecision(
        route="L-EXEC",
        intent=Intent.MODIFY_CODE,
        evidence_scope="work_state",
        provider_allowed=True,
    )

    def handler(_orchestrator, _intent, *, authorized_ask=None, **_kwargs):
        if invoke_provider:
            authorized_ask("authorized code-generation prompt", system="scope")
        return dict(handler_result)

    monkeypatch.setattr(dispatch_module, "dispatch", handler)
    result = dispatch_module.route_request(
        orchestrator,
        Intent.MODIFY_CODE,
        "src/module.py",
        "عدّل الدالة المطلوبة",
        route_decision=decision,
        ask_provider=lambda *args, **kwargs: (
            provider_calls.append((args, kwargs))
            or {"status": "success", "text": "generated patch"}
        ),
    )
    return result, skill_runs, provider_calls


def test_verified_provider_assisted_code_change_records_successful_skill_run(monkeypatch):
    result, skill_runs, provider_calls = _route(
        monkeypatch,
        {
            "status": "success",
            "verified": True,
            "executed": True,
            "text": "patch verified",
        },
    )

    assert result["status"] == "success"
    assert len(provider_calls) == 1
    assert len(skill_runs) == 1
    skill_id, run = skill_runs[0]
    assert skill_id == 17
    assert run["success"] is True
    assert run["context"] == {
        "intent": "modify_code",
        "target": "src/module.py",
        "route": "L-EXEC",
    }


def test_failed_provider_assisted_code_change_records_failure(monkeypatch):
    result, skill_runs, provider_calls = _route(
        monkeypatch,
        {"status": "failed", "executed": False, "text": "validation failed"},
    )

    assert result["status"] == "failed"
    assert len(provider_calls) == 1
    assert len(skill_runs) == 1
    assert skill_runs[0][1]["success"] is False


def test_skill_is_not_marked_run_when_handler_never_calls_provider(monkeypatch):
    result, skill_runs, provider_calls = _route(
        monkeypatch,
        {"status": "needs_clarification", "executed": False},
        invoke_provider=False,
    )

    assert result["status"] == "needs_clarification"
    assert provider_calls == []
    assert skill_runs == []
