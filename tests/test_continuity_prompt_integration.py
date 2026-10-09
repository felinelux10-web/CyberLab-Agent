from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.llm.prompt_builder import build_cybersec_prompt


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
