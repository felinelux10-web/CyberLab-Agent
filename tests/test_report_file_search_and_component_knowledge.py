

def test_process_routes_component_question_to_evidence_chat_not_orchestrator(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as module
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.context.context_store import ContextStore

    captured = {}

    class FakeOrchestrator:
        context = ContextStore()
        def handle(self, *args, **kwargs):
            captured["orchestrator_called"] = True
            return {"status": "failed", "text": "wrong owner"}

    evidence = {
        "type": "component",
        "components": [{
            "name": "conversation_manager",
            "path": "lab_v4_dev/conversation/conversation_manager.py",
            "functions": ["process", "_dispatch"],
            "classes": ["ConversationManager"],
            "imports": ["intent_parser"],
            "related_to": ["lab_v4_dev/core/orchestrator.py"],
        }],
        "current_project_knowledge": True,
    }
    monkeypatch.setattr(module, "retrieve_for_question", lambda question: captured.setdefault("evidence", evidence))
    monkeypatch.setattr(module, "build_chat_prompt", lambda *args, **kwargs: (
        captured.setdefault("prompt", kwargs), "grounded prompt"
    ))
    monkeypatch.setattr(module, "gateway_ask", lambda *args, **kwargs: {
        "status": "success", "text": "إجابة مبنية على الشفرة"
    })

    manager = ConversationManager(FakeOrchestrator())
    result = manager.process("ما وظيفة ConversationManager في مشروع CyberLab Agent الحالي؟")
    assert result["status"] == "success"
    assert "orchestrator_called" not in captured
    assert captured["prompt"]["project_knowledge"]["components"][0]["path"].endswith(
        "conversation_manager.py"
    )


def test_process_keeps_executable_request_with_orchestrator(monkeypatch):
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.context.context_store import ContextStore

    class FakeOrchestrator:
        context = ContextStore()
        def __init__(self):
            self.calls = []
        def handle(self, text, parsed=None, **kwargs):
            self.calls.append((text, parsed))
            return {"status": "success", "intent": parsed["intent"], "text": "تم التنفيذ"}

    orchestrator = FakeOrchestrator()
    manager = ConversationManager(orchestrator)
    result = manager.process("شغّل الاختبارات")
    assert result["status"] == "success"
    assert len(orchestrator.calls) == 1


def test_process_social_message_does_not_retrieve_project_knowledge(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as module
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.context.context_store import ContextStore

    calls = []
    monkeypatch.setattr(module, "retrieve_for_question", lambda question: calls.append(question))
    monkeypatch.setattr(module, "gateway_ask", lambda *args, **kwargs: {
        "status": "success", "text": "أهلًا"
    })

    class FakeOrchestrator:
        context = ContextStore()

    result = ConversationManager(FakeOrchestrator()).process("السلام عليكم")
    assert result["status"] == "success"
    assert calls == []


def test_component_retrieval_rejects_generic_words_and_unknown_component():
    from lab_v4_dev.awareness.knowledge_retriever import KnowledgeRetriever
    from lab_v4_dev.awareness.project_knowledge import ProjectKnowledgeEntity, ProjectKnowledgeModel

    model = ProjectKnowledgeModel(repository_path="/tmp/project")
    model.add_entity(ProjectKnowledgeEntity(
        id="agent", name="agent", type="file", path="lab_v4_dev/core/agent.py",
        layer="core", metadata={"classes": ["Agent"], "functions": ["run"]},
    ))
    model.add_entity(ProjectKnowledgeEntity(
        id="orchestrator", name="orchestrator", type="file", path="lab_v4_dev/core/orchestrator.py",
        layer="core", metadata={"classes": ["Orchestrator"], "functions": ["handle"]},
    ))
    unknown = KnowledgeRetriever(model).retrieve(
        "ما وظيفة MissingComponent987 في مشروع CyberLab الحالي؟"
    )
    assert unknown["components"] == []
    assert "غير كافٍ" in unknown["recommendation"]
    known_by_class = KnowledgeRetriever(model).retrieve(
        "ما وظيفة Orchestrator في المشروع الحالي؟"
    )
    assert [item["path"] for item in known_by_class["components"]] == [
        "lab_v4_dev/core/orchestrator.py"
    ]
    assert known_by_class["components"][0]["match_kind"] == "file"
    known_by_function = KnowledgeRetriever(model).retrieve(
        "ما وظيفة handle في مشروعك الحالي؟"
    )
    assert [item["path"] for item in known_by_function["components"]] == [
        "lab_v4_dev/core/orchestrator.py"
    ]
    assert known_by_function["components"][0]["match_kind"] == "function"


def test_file_search_rejects_parent_absolute_and_symlink_escape(tmp_path, monkeypatch):
    import os
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.intent.intents import Intent

    root = tmp_path / "project"
    root.mkdir()
    inside = root / "inside.py"
    inside.write_text("print('ok')", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')", encoding="utf-8")
    link = root / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        link = None

    monkeypatch.setattr("lab_v4_dev.core.project_context.get_active_project_root", lambda: str(root))
    orchestrator = Orchestrator(type("Agent", (), {"runtime": None})(), context=ContextStore())
    for target in ("../outside.py", str(outside)) + (("link.py",) if link else ()):
        result = orchestrator._route(Intent.SEARCH_CODE, target, "file_operation", target)
        assert "غير موجود" in result["text"]
