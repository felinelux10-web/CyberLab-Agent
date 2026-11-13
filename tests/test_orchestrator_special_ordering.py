from types import SimpleNamespace
import importlib

from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.core.orchestrator_handlers import project_analysis
from lab_v4_dev.intent.intents import Intent


def test_response_cache_precedes_registered_handler_dispatch(monkeypatch):
    from lab_v4_dev.intent import response_cache
    dispatch_module = importlib.import_module("lab_v4_dev.core.orchestrator_handlers.dispatch")

    monkeypatch.setattr(response_cache, "get", lambda intent, target: "cached answer")
    monkeypatch.setattr(
        dispatch_module,
        "dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("registered handler must not run before response cache")
        ),
    )

    orchestrator = object.__new__(Orchestrator)
    result = orchestrator._route(
        Intent.ANALYZE_CODE,
        "lab_v4_dev/core/agent.py",
        "project_level",
        "حلل ملف agent.py",
    )

    assert result["status"] == "success"
    assert result["source"] == "cache"
    assert result["text"] == "cached answer"


def test_file_impact_dependency_question_keeps_specialized_mode_priority(monkeypatch):
    from lab_v4_dev.awareness import dependency_map
    from lab_v4_dev.core import project_context

    calls = []
    monkeypatch.setattr(project_context, "get_active_project_root", lambda: "/tmp/cyberlab")
    monkeypatch.setattr(project_context, "project_index_dir", lambda _root: "/tmp/cyberlab/index")
    monkeypatch.setattr(project_analysis.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(
        dependency_map,
        "get_impact",
        lambda target: calls.append(target) or {"imported_by": ["consumer.py"]},
    )
    facade = SimpleNamespace(services=SimpleNamespace(impact_analyzed=set()))

    result = project_analysis.handle_file_impact(
        facade,
        Intent.FILE_IMPACT,
        target="foo.py",
        raw="ما الملفات التي تعتمد على foo.py؟",
    )

    assert calls == ["foo.py"]
    assert "consumer.py" in result["text"]
    assert "الملفات التي تعتمد على" in result["text"]


def test_file_impact_general_question_keeps_impact_analysis_mode(monkeypatch):
    from lab_v4_dev.awareness import dependency_map
    from lab_v4_dev.core import project_context

    monkeypatch.setattr(
        project_context,
        "get_active_project",
        lambda: SimpleNamespace(root="/tmp/cyberlab", name="cyberlab"),
    )
    monkeypatch.setattr(project_context, "get_active_project_root", lambda: "/tmp/cyberlab")
    monkeypatch.setattr(project_context, "project_index_dir", lambda _root: "/tmp/cyberlab/index")
    monkeypatch.setattr(project_context, "CYBERLAB_ROOT", "/tmp/cyberlab")
    monkeypatch.setattr(project_analysis.os.path, "exists", lambda _path: True)
    calls = []
    monkeypatch.setattr(
        dependency_map,
        "get_impact",
        lambda target: calls.append(target) or {
            "file": target,
            "risk": "high",
            "imports": ["base.py"],
            "imported_by": ["consumer.py"],
        },
    )
    facade = SimpleNamespace(services=SimpleNamespace(impact_analyzed=set()))

    result = project_analysis.handle_file_impact(
        facade,
        Intent.FILE_IMPACT,
        target="foo.py",
        raw="ما تأثير تعديل foo.py",
    )

    assert calls == ["foo.py"]
    assert "تأثير تعديل" in result["text"]
    assert "high" in result["text"]
    assert "foo.py" in facade.services.impact_analyzed
