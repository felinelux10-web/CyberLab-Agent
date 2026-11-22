from types import SimpleNamespace
from unittest.mock import Mock

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.core.contracts import RouteDecision
from lab_v4_dev.core.orchestrator_handlers import execution as execution_module
from lab_v4_dev.intent.intents import Intent


def _make_script_runner(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    scripts = workspace / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "example.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.setattr(
        "lab_v4_dev.core.project_context.CYBERLAB_ROOT",
        str(tmp_path),
    )
    monkeypatch.setattr(
        "lab_v4_dev.core.security_guard.check_path",
        lambda _path: {"safe": True},
    )
    monkeypatch.setattr(
        "lab_v4_dev.core.execution_history.save_run",
        lambda *_args, **_kwargs: None,
    )

    submit = Mock(return_value={
        "status": "executed",
        "results": [{
            "status": "success",
            "stdout": "ok",
            "stderr": "",
            "exit_code": 0,
        }],
    })
    context = ContextStore()
    context.last_result = {"saved_to": str(script)}
    request = SimpleNamespace(
        route_decision=RouteDecision(
            route="L-EXEC",
            intent=Intent.RUN_SCRIPT,
            evidence_scope="work_state",
            provider_allowed=False,
        ),
        response_attributes={},
    )
    orchestrator = SimpleNamespace(
        context=context,
        request=request,
        services=SimpleNamespace(submit_prepared_execution=submit),
    )
    return script, submit, orchestrator


def test_run_script_does_not_reuse_last_saved_file_without_explicit_repeat(monkeypatch, tmp_path):
    _script, submit, orchestrator = _make_script_runner(monkeypatch, tmp_path)

    result = execution_module.handle_run_script(
        orchestrator,
        Intent.RUN_SCRIPT,
        target=None,
        raw="شغل السكريبت",
    )

    assert result["status"] == "needs_clarification"
    assert result["executed"] is False
    submit.assert_not_called()


def test_run_script_reuses_last_saved_file_only_for_explicit_repeat(monkeypatch, tmp_path):
    script, submit, orchestrator = _make_script_runner(monkeypatch, tmp_path)

    result = execution_module.handle_run_script(
        orchestrator,
        Intent.RUN_SCRIPT,
        target=None,
        raw="شغل نفس السكريبت",
    )

    assert result["status"] == "success"
    assert submit.call_count == 1
    assert submit.call_args.kwargs["target"] == str(script.resolve())
