from types import SimpleNamespace

import pytest

from lab_v4_dev.core.contracts import RouteDecision
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intents import Intent


def test_effectful_intents_require_a_final_route_and_work_evidence():
    intents = (
        Intent.CLEAN_DEVICE,
        Intent.DELETE_FILE,
        Intent.MODIFY_CODE,
        Intent.RUN_SCRIPT,
        Intent.REPAIR_APPROVE,
    )
    for intent in intents:
        orchestrator = object.__new__(Orchestrator)
        denied = orchestrator.handle("explicit operation", parsed={"intent": intent})
        assert denied["status"] == "denied"
        assert denied["source"] == "route_decision_required"

        wrong_scope = RouteDecision(
            route="L-EXEC",
            evidence_scope="project_state",
            intent=intent,
        )
        denied = orchestrator.handle(
            "explicit operation",
            parsed={"intent": intent},
            route_decision=wrong_scope,
        )
        assert denied["status"] == "denied"
        assert denied["source"] == "route_decision_work_evidence_guard"


def test_clean_device_preserves_legacy_cleaner_effect_and_report(monkeypatch):
    from lab_v4_dev.core import cleaner
    from lab_v4_dev.core.orchestrator_handlers.maintenance import handle_clean_device

    calls = []
    monkeypatch.setattr(cleaner, "run_full_clean", lambda: calls.append("clean") or {
        "before_mb": 100.0,
        "after_mb": 110.0,
        "freed_mb": 10.0,
        "freed_kb": 10240.0,
        "details": [{"type": "tmp", "removed": 2, "size_kb": 10240.0}],
    })

    result = handle_clean_device(SimpleNamespace(), Intent.CLEAN_DEVICE)

    assert calls == ["clean"]
    assert result["status"] == "success"
    assert "10.0 MB" in result["text"]
    assert "tmp: حذف 2 عنصر" in result["text"]


def test_delete_file_preserves_safe_delete_backup_and_snapshot_contract(monkeypatch):
    from lab_v4_dev.core import safe_io
    from lab_v4_dev.core.orchestrator_handlers.maintenance import handle_delete_file

    calls = []
    monkeypatch.setattr(safe_io, "safe_delete", lambda path, reason: calls.append((path, reason)) or {
        "status": "success",
        "backup": path + ".bak",
        "snapshot": "snapshot-1",
    })
    facade = SimpleNamespace(context=SimpleNamespace(current_file="lab_v4_dev/sample.py"))

    result = handle_delete_file(facade, Intent.DELETE_FILE)

    assert calls == [("lab_v4_dev/sample.py", "user request")]
    assert result["status"] == "success"
    assert result["backup"] == "lab_v4_dev/sample.py.bak"
    assert result["snapshot"] == "snapshot-1"


def test_run_script_preserves_explicit_script_selection_and_sandbox_execution(monkeypatch, tmp_path):
    from lab_v4_dev.core import project_context, sandbox_executor
    from lab_v4_dev.core.orchestrator_handlers.execution import handle_run_script

    scripts = tmp_path / "workspace" / "scripts"
    scripts.mkdir(parents=True)
    selected = scripts / "selected.py"
    other = scripts / "other.py"
    selected.write_text("print('selected')\n", encoding="utf-8")
    other.write_text("print('other')\n", encoding="utf-8")
    monkeypatch.setattr(project_context, "CYBERLAB_ROOT", str(tmp_path))

    calls = []
    monkeypatch.setattr(sandbox_executor, "run_code", lambda path, timeout=10: calls.append((path, timeout)) or {
        "status": "success", "duration": 0.1, "exit_code": 0, "output": "selected",
    })

    result = handle_run_script(
        SimpleNamespace(context=SimpleNamespace(last_result=None)),
        Intent.RUN_SCRIPT,
        raw="شغّل selected.py",
    )

    assert calls == [(str(selected), 10)]
    assert result["status"] == "success"
    assert "selected.py" in result["text"]


def test_repair_approve_preserves_explicit_pending_fix_application(monkeypatch):
    from lab_v4_dev.core.repair import diff_approval
    from lab_v4_dev.core.orchestrator_handlers.repair import handle_repair_approve

    calls = []
    monkeypatch.setattr(diff_approval, "apply_fix", lambda path, approved=False: calls.append((path, approved)) or {
        "status": "success", "message": "تم التعديل",
    })
    facade = SimpleNamespace(context=SimpleNamespace(last_result={"pending_path": "workspace/pending_fixes/fix.json"}))

    result = handle_repair_approve(facade, Intent.REPAIR_APPROVE)

    assert calls == [("workspace/pending_fixes/fix.json", True)]
    assert result["status"] == "success"
    assert "تم التعديل" in result["text"]


def test_repair_analyze_preserves_provider_capability_and_pending_proposal(monkeypatch):
    from lab_v4_dev.core.repair import error_reader, error_analyzer, fix_generator, diff_approval
    from lab_v4_dev.core.orchestrator_handlers.repair import handle_repair_analyze

    provider = object()
    calls = []
    monkeypatch.setattr(error_reader, "get_latest_error", lambda: {"message": "ValueError", "file": "main.py"})
    monkeypatch.setattr(error_analyzer, "analyze", lambda error, authorized_ask=None: calls.append(("analyze", authorized_ask)) or {"fixable": True})
    monkeypatch.setattr(fix_generator, "generate_fix", lambda error, analysis, authorized_ask=None: calls.append(("generate", authorized_ask)) or {"description": "fix"})
    monkeypatch.setattr(diff_approval, "show_fix_proposal", lambda fix, error: "proposal")
    monkeypatch.setattr(diff_approval, "save_pending_fix", lambda *args: "workspace/pending_fixes/fix.json")
    facade = SimpleNamespace(context=SimpleNamespace(last_result=None))

    result = handle_repair_analyze(facade, Intent.REPAIR_ANALYZE, authorized_ask=provider)

    assert calls == [("analyze", provider), ("generate", provider)]
    assert result["status"] == "success"
    assert result["text"] == "proposal"
    assert facade.context.last_result["pending_path"] == "workspace/pending_fixes/fix.json"


def test_modify_code_preserves_safe_pipeline_write_and_post_write_verification(monkeypatch, tmp_path):
    from lab_v4_dev.core import code_engine, surgical_editor, symbol_resolver
    from lab_v4_dev.core.orchestrator_handlers.code_authoring import handle_modify_code

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n", encoding="utf-8")

    monkeypatch.setattr(symbol_resolver, "resolve", lambda raw, target: {
        "found": True, "file": str(source), "symbol": None,
    })
    monkeypatch.setattr(surgical_editor, "extract_symbol", lambda path, symbol: {})
    monkeypatch.setattr(code_engine, "modify_code", lambda code, instruction, authorized_ask=None: {
        "status": "success", "code": "value = 2\n",
    })

    class Pipeline:
        def execute(self, plan, changes):
            assert plan["files"] == [str(source)]
            source.write_text(changes[str(source)], encoding="utf-8")
            return {"status": "success"}

    facade = SimpleNamespace(
        context=SimpleNamespace(current_file=None),
        services=SimpleNamespace(db=None),
        pipeline=Pipeline(),
    )

    result = handle_modify_code(
        facade,
        Intent.MODIFY_CODE,
        raw="عدّل sample.py واجعل القيمة اثنين",
        authorized_ask=lambda *args, **kwargs: {"status": "success", "text": "ok"},
    )

    assert result["status"] == "success"
    assert result["verified"] is True
    assert source.read_text(encoding="utf-8") == "value = 2\n"
    assert facade.context.current_file == str(source)
