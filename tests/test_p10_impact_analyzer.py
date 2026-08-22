from lab_v4_dev.planner.impact_analyzer import ImpactAnalyzer


def test_impact_analyzer_returns_contract(monkeypatch):
    graph = {
        "target.py": ["direct.py"],
        "direct.py": ["indirect.py"],
        "indirect.py": [],
    }

    monkeypatch.setattr(
        "lab_v4_dev.planner.impact_analyzer.get_importers",
        lambda path: graph.get(path, []),
    )

    result = ImpactAnalyzer().analyze("target.py")

    assert result.target == "target.py"
    assert result.affected == ("direct.py", "indirect.py")
    assert result.level == "direct"


def test_impact_analyzer_without_dependents():
    result = ImpactAnalyzer().analyze("unknown_target.py")

    assert result.target == "unknown_target.py"
    assert result.affected == ()
    assert result.level == "unknown"


def test_legacy_wrapper_returns_dict(monkeypatch):
    monkeypatch.setattr(
        "lab_v4_dev.planner.impact_analyzer.get_importers",
        lambda path: ["dependent.py"] if path == "target.py" else [],
    )

    from lab_v4_dev.planner.impact_analyzer import analyze_impact

    result = analyze_impact("target.py")

    assert isinstance(result, dict)
    assert result["target"] == "target.py"
    assert result["affected"] == ["dependent.py"]
