from types import SimpleNamespace

from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intents import Intent


def _orchestrator(*, current_file=None, last_result=None, analyzed=(), impacted=()):
    instance = object.__new__(Orchestrator)
    instance.context = SimpleNamespace(
        current_file=current_file,
        last_result=last_result,
    )
    instance._analyzed_files = set(analyzed)
    instance._impact_analyzed = set(impacted)
    return instance


def test_profile_load_failure_keeps_conservative_modify_gate(monkeypatch):
    from lab_v4_dev.user_data import profile_loader

    def unavailable():
        raise OSError("profile unavailable")

    monkeypatch.setattr(profile_loader, "load_profile", unavailable)
    orchestrator = _orchestrator()

    result = orchestrator._pre_handler_policy(
        Intent.MODIFY_CODE,
        "src/module.py",
        "عدّل src/module.py",
    )

    assert result["status"] == "blocked"
    assert result["source"] == "profile_analysis_required"


def test_allow_guessing_false_rejects_implicit_context_file_selection(monkeypatch):
    from lab_v4_dev.user_data import profile_loader

    monkeypatch.setattr(profile_loader, "load_profile", lambda: {
        "trust_policy": {"allow_guessing": False},
        "engineering_style": {
            "analyze_before_modify": False,
            "require_impact_analysis": False,
        },
    })
    orchestrator = _orchestrator(current_file="src/previous.py")

    result = orchestrator._pre_handler_policy(
        Intent.MODIFY_CODE,
        None,
        "عدّل الملف",
    )

    assert result["status"] == "needs_clarification"
    assert result["source"] == "profile_no_implicit_target"


def test_impact_analysis_exception_fails_closed(monkeypatch):
    from lab_v4_dev.user_data import profile_loader
    from lab_v4_dev.awareness import dependency_map

    monkeypatch.setattr(profile_loader, "load_profile", lambda: {
        "trust_policy": {"allow_guessing": True},
        "engineering_style": {
            "analyze_before_modify": False,
            "require_impact_analysis": True,
        },
    })

    def fail(_target):
        raise RuntimeError("dependency index unavailable")

    monkeypatch.setattr(dependency_map, "get_impact", fail)
    orchestrator = _orchestrator()

    result = orchestrator._pre_handler_policy(
        Intent.MODIFY_CODE,
        "src/module.py",
        "عدّل src/module.py",
    )

    assert result["status"] == "blocked"
    assert result["source"] == "profile_impact_analysis_failed"
    assert "dependency index unavailable" in result["text"]
    assert "src/module.py" not in orchestrator._impact_analyzed


def test_unknown_impact_result_is_not_cached_as_a_successful_analysis(monkeypatch):
    from lab_v4_dev.user_data import profile_loader
    from lab_v4_dev.awareness import dependency_map

    monkeypatch.setattr(profile_loader, "load_profile", lambda: {
        "trust_policy": {"allow_guessing": True},
        "engineering_style": {
            "analyze_before_modify": False,
            "require_impact_analysis": True,
        },
    })
    monkeypatch.setattr(
        dependency_map,
        "get_impact",
        lambda _target: {"file": "src/module.py", "risk": "unknown", "impact": []},
    )
    orchestrator = _orchestrator()

    result = orchestrator._pre_handler_policy(
        Intent.MODIFY_CODE,
        "src/module.py",
        "عدّل src/module.py",
    )

    assert result["status"] == "blocked"
    assert result["source"] == "profile_impact_analysis_incomplete"
    assert "src/module.py" not in orchestrator._impact_analyzed


def test_successful_impact_analysis_is_cached_for_the_exact_target(monkeypatch):
    from lab_v4_dev.user_data import profile_loader
    from lab_v4_dev.awareness import dependency_map

    monkeypatch.setattr(profile_loader, "load_profile", lambda: {
        "trust_policy": {"allow_guessing": True},
        "engineering_style": {
            "analyze_before_modify": False,
            "require_impact_analysis": True,
        },
    })
    calls = []
    monkeypatch.setattr(
        dependency_map,
        "get_impact",
        lambda target: calls.append(target) or {
            "file": target,
            "risk": "low",
            "imports": [],
            "imported_by": [],
        },
    )
    orchestrator = _orchestrator()

    assert orchestrator._pre_handler_policy(
        Intent.MODIFY_CODE, "src/module.py", "عدّل src/module.py"
    ) is None
    assert calls == ["src/module.py"]
    assert orchestrator._impact_analyzed == {"src/module.py"}


def test_allow_guessing_false_requires_explicit_pending_repair_selection(monkeypatch):
    from lab_v4_dev.user_data import profile_loader

    monkeypatch.setattr(profile_loader, "load_profile", lambda: {
        "trust_policy": {"allow_guessing": False},
        "engineering_style": {
            "analyze_before_modify": False,
            "require_impact_analysis": False,
        },
    })
    orchestrator = _orchestrator()

    result = orchestrator._pre_handler_policy(
        Intent.REPAIR_APPROVE,
        None,
        "وافق على الإصلاح",
    )

    assert result["status"] == "needs_clarification"
    assert result["source"] == "profile_no_implicit_repair_selection"
