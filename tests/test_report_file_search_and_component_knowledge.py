from types import SimpleNamespace


def test_parser_extracts_explicit_paths_without_punctuation_or_fake_target():
    from lab_v4_dev.intent.intent_parser import parse
    from lab_v4_dev.intent.intents import Intent

    for question, expected in (
        (
            "هل الملف lab_v4_dev/conversation/conversation_manager.py موجود في مشروعك؟",
            "lab_v4_dev/conversation/conversation_manager.py",
        ),
        (
            "هل الملف lab_v4_dev/core/agent.py موجود في المشروع؟",
            "lab_v4_dev/core/agent.py",
        ),
    ):
        result = parse(question)
        assert result["intent"] == Intent.SEARCH_CODE
        assert result["target"] == expected
        assert result["target"] not in {"المشروع", "مشروعك"}


def test_search_route_uses_filesystem_evidence_and_never_calls_llm(monkeypatch):
    import lab_v4_dev.core.orchestrator as module
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.intent.intents import Intent

    root = "/tmp/CyberLab-Agent-audit"
    target = "lab_v4_dev/core/agent.py"
    monkeypatch.setattr("lab_v4_dev.core.project_context.get_active_project_root", lambda: root)
    monkeypatch.setattr(module, "ask", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("explicit local file search must not call LLM")
    ))
    monkeypatch.setattr(module, "get_active_provider", lambda: "unused")
    monkeypatch.setattr("lab_v4_dev.awareness.project_index.search_index", lambda query: [{
        "path": target, "role": "agent", "score": 3,
    }])
    monkeypatch.setattr("lab_v4_dev.awareness.project_index.save_index", lambda: None)

    orchestrator = Orchestrator(SimpleNamespace(runtime=None))
    result = orchestrator._route(
        Intent.SEARCH_CODE, target, "file_operation", "هل الملف موجود؟"
    )
    assert result["evidence"] == "filesystem_check_and_project_index"
    assert target in result["text"]


def test_missing_explicit_path_is_not_replaced_by_last_question_word(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.intent.intents import Intent

    orchestrator = Orchestrator(SimpleNamespace(runtime=None))
    monkeypatch.setattr("lab_v4_dev.core.project_context.get_active_project_root", lambda: "/tmp/CyberLab-Agent-audit")
    monkeypatch.setattr("lab_v4_dev.core.orchestrator.os.path.isfile", lambda path: False if path.endswith("not_real.py") else True)
    monkeypatch.setattr("lab_v4_dev.awareness.project_index.search_index", lambda query: (_ for _ in ()).throw(
        AssertionError("missing explicit path must not become a keyword search")
    ))
    result = orchestrator._route(
        Intent.SEARCH_CODE,
        "lab_v4_dev/not_real.py",
        "file_operation",
        "هل الملف lab_v4_dev/not_real.py موجود في المشروع؟",
    )
    assert "غير موجود" in result["text"]


def test_component_questions_retrieve_component_evidence(monkeypatch):
    from lab_v4_dev.awareness.knowledge_retriever import KnowledgeRetriever
    from lab_v4_dev.awareness.project_knowledge import ProjectKnowledgeEntity, ProjectKnowledgeModel

    model = ProjectKnowledgeModel(repository_path="/tmp/project")
    model.add_entity(ProjectKnowledgeEntity(
        id="conversation", name="conversation_manager", type="file",
        path="lab_v4_dev/conversation/conversation_manager.py", layer="conversation",
        metadata={"functions": ["process"], "classes": ["ConversationManager"], "imports": ["intent_parser"]},
    ))
    model.add_entity(ProjectKnowledgeEntity(
        id="orchestrator", name="orchestrator", type="file",
        path="lab_v4_dev/core/orchestrator.py", layer="core",
        metadata={"functions": ["handle", "_route"], "classes": ["Orchestrator"]},
    ))
    result = KnowledgeRetriever(model).retrieve(
        "ما الفرق بين ConversationManager وOrchestrator في بنية CyberLab Agent الحالية؟"
    )
    assert result["type"] == "component"
    paths = {item["path"] for item in result["components"]}
    assert "lab_v4_dev/conversation/conversation_manager.py" in paths
    assert "lab_v4_dev/core/orchestrator.py" in paths


def test_conversation_manager_retrieves_project_knowledge_for_component_question(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as module
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.context.context_store import ContextStore

    captured = {}
    monkeypatch.setattr(module, "retrieve_for_question", lambda question: captured.setdefault(
        "knowledge", {"type": "component", "current_project_knowledge": True}
    ))
    monkeypatch.setattr(module, "build_chat_prompt", lambda *args, **kwargs: (
        captured.setdefault("prompt", kwargs), "prompt"
    ))
    monkeypatch.setattr(module, "gateway_ask", lambda *args, **kwargs: {
        "status": "success", "text": "إجابة مؤسسة على الأدلة"
    })

    class FakeOrchestrator:
        context = ContextStore()

    manager = ConversationManager(FakeOrchestrator())
    result = manager._handle_chat(
        "ما هو دور ConversationManager في مشروعك؟",
        "chat",
        parsed={"intent": "cyber_explain", "conversation_domain": "project", "conversation_act": "NONE", "response_attributes": {}},
        user_question="ما هو دور ConversationManager في مشروعك؟",
    )
    assert result["status"] == "success"
    assert captured["knowledge"]["type"] == "component"


def test_component_prompt_contains_functions_imports_and_relationships():
    from lab_v4_dev.llm.prompt_builder import _format_retrieved_knowledge

    text = _format_retrieved_knowledge({
        "type": "component",
        "components": [{
            "name": "conversation_manager",
            "path": "lab_v4_dev/conversation/conversation_manager.py",
            "functions": ["process"],
            "imports": ["intent_parser"],
            "related_to": ["lab_v4_dev/core/orchestrator.py"],
        }],
    })
    assert "conversation_manager" in text
    assert "process" in text
    assert "intent_parser" in text
    assert "orchestrator.py" in text
