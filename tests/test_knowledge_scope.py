from types import SimpleNamespace

from lab_v4_dev.awareness.knowledge_retriever import (
    KnowledgeRetriever,
    ProjectScope,
    resolve_project_scope,
)


def _retriever():
    model = SimpleNamespace(
        layers={"lab_v4_dev": "application namespace"},
        entry_points=["run.py"],
        entities={},
        relationships=[],
    )
    return KnowledgeRetriever(model)


def test_scope_resolution_requires_evidence_for_current_project():
    assert resolve_project_scope("من أنت؟") == ProjectScope.CURRENT_PROJECT
    assert resolve_project_scope("كيف يعمل ConversationManager في مشروعك؟") == ProjectScope.CURRENT_PROJECT
    assert resolve_project_scope("أي مشروع غير مشروعنا") == ProjectScope.EXTERNAL_PROJECT
    assert resolve_project_scope("تحدث عن أي مشروع آخر") == ProjectScope.EXTERNAL_PROJECT
    assert resolve_project_scope("ما هي مراحل تطوير مشروع؟") == ProjectScope.GENERIC_PROJECT
    assert resolve_project_scope("مشروع في الفضاء") == ProjectScope.EXTERNAL_PROJECT
    assert resolve_project_scope("كيف كان المشروع سابقاً؟") == ProjectScope.HISTORICAL_PROJECT
    assert resolve_project_scope("ما هو المشروع؟") == ProjectScope.GENERIC_PROJECT


def test_external_and_generic_questions_do_not_receive_current_snapshot():
    retriever = _retriever()

    for question, expected_scope in (
        ("أي مشروع غير مشروعنا", ProjectScope.EXTERNAL_PROJECT),
        ("كيف أعمل على مشروع بشكل صحيح؟", ProjectScope.GENERIC_PROJECT),
        ("مشروع وهمي", ProjectScope.EXTERNAL_PROJECT),
        ("سؤال غير محدد", ProjectScope.UNKNOWN),
    ):
        result = retriever.retrieve(question)
        assert result["project_scope"] == expected_scope
        assert result["current_project_knowledge"] is False
        assert "layers" not in result
        assert "entry_points" not in result
        assert "total_files" not in result


def test_current_project_question_preserves_existing_retrieval():
    result = _retriever().retrieve("ما هي طبقات مشروع CyberLab Agent؟")

    assert result["project_scope"] == ProjectScope.CURRENT_PROJECT
    assert result["current_project_knowledge"] is True
    assert result["layers"] == ["lab_v4_dev"]
    assert result["entry_points"] == ["run.py"]
