from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.llm.prompt_builder import build_cybersec_prompt
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intents import Intent


class CapturingOrchestrator:
    def __init__(self):
        self.calls = []
        self.context = ContextStore()

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append({"text": text, "parsed": dict(parsed or {}), "kwargs": kwargs})
        return {
            "status": "success",
            "intent": (parsed or {}).get("intent"),
            "target": (parsed or {}).get("target"),
            "text": "رد الفرع الحالي",
        }


def test_executable_explanation_receives_selected_branch_history(monkeypatch):
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    manager.process("اشرح CSRF")
    result = manager.process("ارجع لشرح SQL Injection")

    assert result["status"] == "success"
    call = orchestrator.calls[-1]
    history = call["kwargs"]["conversation_history"]
    assert any(item.get("content") == "اشرح SQL Injection" for item in history)
    assert all(item.get("content") != "اشرح CSRF" for item in history)
    assert call["kwargs"]["context_transition"] == "restore"


def test_explicit_independent_topic_does_not_receive_previous_branch():
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    result = manager.process(
        "اشرح CSRF بالتفصيل، وابدأ شرحًا مستقلًا عن الموضوع السابق"
    )

    assert result["status"] == "success"
    call = orchestrator.calls[-1]
    assert call["kwargs"]["conversation_history"] == []
    assert call["kwargs"]["context_transition"] == "new_independent"


def test_cyber_prompt_contains_branch_history_and_resume_instruction():
    system, prompt = build_cybersec_prompt(
        "SQL Injection",
        history=[
            {"role": "user", "content": "اشرح SQL Injection"},
            {"role": "assistant", "content": "توقفنا عند آلية الحدوث."},
        ],
        continuation=True,
    )
    assert "توقفنا عند آلية الحدوث" in prompt
    assert "لا تبدأ الشرح من الصفر" in prompt
    assert "SQL Injection" in prompt
    assert "أنت خبير أمن سيبراني" in system


def test_conversation_history_question_uses_dialogue_memory_not_project_context(monkeypatch):
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    manager.process("اشرح CSRF")
    result = manager.process("ما الموضوعين اللذين شرحتَهما؟")

    assert result["source"] == "dialogue_memory"
    assert result["topics"] == ["SQL Injection", "CSRF"]
    assert "SQL Injection" in result["text"]
    assert "CSRF" in result["text"]


def test_generic_topic_references_resolve_from_dialogue_topics_only():
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    manager.process("اشرح CSRF")

    first = manager.process("ارجع الى الموضوع الاول")
    assert first["status"] == "success"
    assert orchestrator.calls[-1]["parsed"]["target"] == "SQL Injection"
    assert first["semantic_request"]["context_transition"] == "restore"

    previous = manager.process("ارجع إلى الموضوع السابق")
    assert previous["status"] == "success"
    assert orchestrator.calls[-1]["parsed"]["target"] == "SQL Injection"
    assert previous["intent"] == "cyber_explain"


def test_provider_privacy_error_is_not_rendered_as_debug_dump(monkeypatch):
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.context.context_store import ContextStore

    monkeypatch.setattr(orchestrator_module, "ask", lambda *args, **kwargs: {
        "status": "error",
        "text": "internal provider details",
        "error": {"code": "PRIVACY_EXTERNAL_BLOCKED"},
    })
    monkeypatch.setattr(orchestrator_module, "get_active_provider", lambda: "gateway")
    monkeypatch.setattr(
        "lab_v4_dev.awareness.knowledge_base.search",
        lambda *_args, **_kwargs: None,
    )

    agent = type("Agent", (), {"db": None})()
    orchestrator = Orchestrator(agent, ContextStore())
    result = orchestrator._route(
        Intent.CYBER_EXPLAIN,
        "CSRF",
        "general",
        "اشرح CSRF",
        conversation_history=[],
        context_transition="new_independent",
    )

    assert "LLM ERROR DEBUG" not in result["text"]
    assert "internal provider details" not in result["text"]
    assert "الخصوصية" in result["text"]


def test_dialogue_recall_without_dialogue_does_not_fall_back_to_work_history():
    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("ارجع إلى الموضوع السابق")

    assert result["status"] == "needs_clarification"
    assert result["source"] == "dialogue_memory"
    assert "آخر المهام" not in result["text"]
    assert result["semantic_request"]["context_kind"] == "dialogue"
    assert orchestrator.calls == []


def test_work_request_is_marked_work_without_using_dialogue_recall():
    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("استكمل العمل في الملف lab_v4_dev/core/agent.py")

    assert result["status"] == "success"
    assert result["semantic_request"]["context_kind"] == "work"
