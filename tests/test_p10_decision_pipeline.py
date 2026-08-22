from lab_v4_dev.planner.decision_pipeline import (
    P10DecisionAssessment,
    P10DecisionPipeline,
)


def test_p10_pipeline_produces_canonical_chain(monkeypatch):
    class FakeImpact:
        target = "target.py"
        affected = ("consumer.py",)
        level = "direct"
        reason = "dependency impact analysis"

        def to_dict(self):
            return {
                "target": self.target,
                "affected": list(self.affected),
                "affected_count": len(self.affected),
                "level": self.level,
                "reason": self.reason,
            }

    monkeypatch.setattr(
        "lab_v4_dev.planner.decision_pipeline.ImpactAnalyzer.analyze",
        lambda self, target: FakeImpact(),
    )

    result = P10DecisionPipeline().assess("target.py")

    assert isinstance(result, P10DecisionAssessment)
    assert len(result.priority) == 1
    assert len(result.risk) == 1
    assert len(result.decisions) == 1
    assert result.priority[0].priority == "critical"
    assert result.risk[0].risk == "high"
    assert result.decisions[0].action == "auto_apply"


def test_p10_pipeline_is_declarative():
    result = P10DecisionPipeline()

    assert hasattr(result, "assess")
    assert not hasattr(result, "execute")
    assert not hasattr(result, "apply")
    assert not hasattr(result, "rollback")
