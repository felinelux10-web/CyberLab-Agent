from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.llm.prompt_builder import build_cybersec_prompt
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.intent.intent_parser import parse


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


def test_bare_resume_does_not_restore_old_work_session_implicitly():
    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("تمام اكمل ايضا")

    assert result["status"] == "needs_clarification"
    assert result["source"] == "conversation_manager"
    assert "استكمال العمل" in result["text"]
    assert result["semantic_request"]["context_kind"] == "unknown"
    assert orchestrator.calls == []


def test_social_state_and_greeting_are_local_without_gateway(monkeypatch):
    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("gateway called")),
    )

    state = manager.process("كيف الحال اليوم")
    friendly = manager.process("اريد حوار ودي عادي")

    assert state["source"] == "local_social"
    assert friendly["source"] == "local_social"
    assert state["semantic_request"]["context_kind"] == "social"
    assert "كيف حالك" in state["text"]


def test_project_word_inside_social_sentence_does_not_trigger_project_scan():
    for text in (
        "لماذا تظهر المشروع",
        "اي كلمة فيها المشروع",
        "مشروع",
        "دعنا نتحدث عنك انت كوكيل في هذا المشروع",
    ):
        parsed = parse(text)
        assert parsed["intent"] != Intent.PROJECT_SCAN

    assert parse("ما هو المشروع الحالي")["intent"] == Intent.SWITCH_PROJECT
    assert parse("ما هي المشاريع التي اشتغلت عليها فعليا")["intent"] == Intent.PROJECT_INDEX


def test_previous_dialogue_phrases_are_not_operational_history():
    for text in ("الحوار السابق", "النقاش السابق", "الحديث السابق"):
        parsed = parse(text)
        assert parsed["intent"] == Intent.PERSONAL_CHAT
        assert parsed["conversation_act"] == "TOPIC_RETURN"


def test_social_dialogue_is_saved_as_typed_memory_and_recalled_without_work_history(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {"status": "success", "text": "رد حواري"},
    )
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("ماذا تقترح انت")
    manager.process("دعنا نتحدث محادثة ودية")
    manager.process("موضوع عام عن التقنية")

    result = manager.process("ماذا كنا نقول في الردود السابقة؟")
    assert result["source"] == "dialogue_memory"
    assert "ماذا تقترح انت" in result["text"]
    assert "موضوع عام عن التقنية" in result["text"]
    assert "آخر المهام" not in result["text"]
    assert all(
        turn.get("context_kind") in {"social", "dialogue"}
        for turn in memory.state.history
        if turn.get("role") == "user"
    )


def test_return_to_social_dialogue_does_not_ask_for_work_or_learning_context(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {"status": "success", "text": "رد حواري"},
    )
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    manager.process("موضوع عام عن التقنية")

    result = manager.process("ارجع للنقاش السابق")
    assert result["source"] == "dialogue_memory"
    assert "سياق العمل" not in result["text"]
    assert "موضوع عام عن التقنية" in result["text"]


def test_dialogue_recall_contains_both_roles_and_survives_prompt_window(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    replies = iter(["اقتراح أول محدد", "اقتراح ثان محدد", "اقتراح ثالث محدد"])
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {"status": "success", "text": next(replies)},
    )
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    manager.process("أعطني اقتراحات")
    manager.process("ماذا أيضًا؟")
    manager.process("أعطني اقتراحات أكثر")

    result = manager.process("ماذا كنا نقول قبل قليل في الردود السابقة؟")
    assert result["source"] == "dialogue_memory"
    assert "اقتراح أول محدد" in result["text"]
    assert "اقتراح ثان محدد" in result["text"]
    assert "المستخدم:" in result["text"]
    assert "الوكيل:" in result["text"]
