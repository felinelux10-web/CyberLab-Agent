from lab_v4_dev.awareness.knowledge_retriever import ProjectScope
from lab_v4_dev.llm.prompt_builder import build_chat_prompt, build_project_context


CURRENT_KNOWLEDGE = {
    "type": "architecture",
    "layers": ["CURRENT_ONLY_LAYER"],
    "entry_points": ["CURRENT_ONLY_ENTRY"],
    "current_project_knowledge": True,
}


def test_project_context_denies_by_default_without_authorized_scope():
    assert build_project_context() == ""
    assert build_project_context(question="مشروع وهمي") == ""
    assert build_project_context(
        project_scope=ProjectScope.GENERIC_PROJECT,
        question="ما هو المشروع الجيد؟",
    ) == ""


def test_prompt_builder_blocks_current_knowledge_for_external_and_generic_scope():
    for question, scope in (
        ("أي مشروع غير مشروعنا", ProjectScope.EXTERNAL_PROJECT),
        ("ما هي مراحل تطوير مشروع؟", ProjectScope.GENERIC_PROJECT),
        ("كيف كان المشروع سابقاً؟", ProjectScope.HISTORICAL_PROJECT),
    ):
        system, _ = build_chat_prompt(
            question,
            project_scope=scope,
            project_knowledge=CURRENT_KNOWLEDGE,
        )
        assert "CURRENT_ONLY_LAYER" not in system
        assert "الملفات الحقيقية في المشروع" not in system


def test_prompt_builder_allows_current_knowledge_only_with_current_scope():
    system, _ = build_chat_prompt(
        "ما هي طبقات مشروع CyberLab Agent؟",
        project_scope=ProjectScope.CURRENT_PROJECT,
        project_knowledge=CURRENT_KNOWLEDGE,
    )
    assert "CURRENT_ONLY_LAYER" in system
