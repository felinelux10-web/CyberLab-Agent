from lab_v4_dev.awareness.knowledge_retriever import (
    KnowledgeRetriever,
    ProjectScope,
    extract_file_paths,
    normalize_project_question,
    resolve_project_scope,
)
from lab_v4_dev.awareness.project_knowledge import (
    ProjectKnowledgeEntity,
    ProjectKnowledgeModel,
)


def test_project_question_normalization_preserves_canonical_file_path():
    question = "هل الملف lab_v4_dev/core/agent.py موجود فعلًا؟"
    assert normalize_project_question(question).endswith("فعلًا")
    assert extract_file_paths(question) == ["lab_v4_dev/core/agent.py"]
    assert resolve_project_scope(question) == ProjectScope.CURRENT_PROJECT


def test_file_retrieval_ignores_question_particle_as_search_target():
    model = ProjectKnowledgeModel(repository_path="/tmp/project")
    model.add_entity(ProjectKnowledgeEntity(
        id="agent", name="agent.py", type="file",
        path="lab_v4_dev/core/agent.py", layer="core",
        metadata={"functions": ["run"], "classes": ["Agent"]},
    ))
    model.add_entity(ProjectKnowledgeEntity(
        id="other", name="other.py", type="file",
        path="lab_v4_dev/core/other.py", layer="core",
    ))

    result = KnowledgeRetriever(model).retrieve(
        "هل الملف lab_v4_dev/core/agent.py موجود فعلًا؟"
    )
    assert result["type"] == "file"
    assert [item["path"] for item in result["matching_files"]] == [
        "lab_v4_dev/core/agent.py"
    ]


def test_dummy_provider_is_explicit_fallback_not_success(monkeypatch):
    from lab_v4_dev.llm import gateway
    from lab_v4_dev.llm.contracts import LLMResponse

    monkeypatch.setattr(gateway, "privacy", type("P", (), {
        "inspect": staticmethod(lambda text: {
            "allow_external": True, "privacy_level": "public",
            "sanitized": text, "reasons": [], "redactions": [],
        }),
        "sanitize": staticmethod(lambda text: text),
    })())
    monkeypatch.setattr(gateway, "route", lambda _: type("D", (), {"provider": "dummy"})())
    monkeypatch.setattr(gateway, "get_fallback_provider", lambda: "dummy")
    monkeypatch.setattr(gateway, "is_provider_enabled", lambda _: True)
    monkeypatch.setattr(gateway, "is_provider_available", lambda name: name == "dummy")
    monkeypatch.setattr(gateway, "get_provider", lambda _: type(
        "Provider", (), {"execute": lambda self, request: LLMResponse.fallback(
            "fallback", provider="dummy", model="dummy"
        )}
    )())

    result = gateway.ask("hello")
    assert result["status"] == "fallback"
    assert result["fallback_used"] is True
