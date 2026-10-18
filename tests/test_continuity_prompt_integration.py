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

    def fake_gateway(prompt, **_kwargs):
        if "ماذا كنا نقول في الردود السابقة" in prompt:
            raise AssertionError("dialogue-history recall must use the grounded local archive")
        return {"status": "success", "text": "رد حواري"}

    monkeypatch.setattr(manager_module, "gateway_ask", fake_gateway)
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("ماذا تقترح انت")
    manager.process("دعنا نتحدث محادثة ودية")
    manager.process("موضوع عام عن التقنية")

    result = manager.process("ماذا كنا نقول في الردود السابقة؟")
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "summary"
    assert "ماذا تقترح انت" in result["text"]
    assert "موضوع عام عن التقنية" in result["text"]
    assert "رد حواري" in result["text"]
    assert "آخر المهام" not in result["text"]
    assert all(
        turn.get("context_kind") in {"social", "dialogue"}
        for turn in memory.state.history
        if turn.get("role") == "user"
    )

def test_return_to_social_dialogue_continues_saved_branch_without_work_context(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    prompts = []

    def fake_gateway(prompt, **_kwargs):
        prompts.append(str(prompt))
        return {"status": "success", "text": "رد حواري"}

    monkeypatch.setattr(manager_module, "gateway_ask", fake_gateway)
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    manager.process("موضوع عام عن التقنية")

    result = manager.process("ارجع للنقاش السابق")
    assert result["status"] == "success"
    assert "رد حواري" in result["text"]
    assert prompts
    assert "موضوع عام عن التقنية" in prompts[-1]
    assert "آخر المهام" not in prompts[-1]


def test_targetless_generic_suggestions_stay_on_conversation_gateway(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {"status": "success", "text": "اقتراح حواري"},
    )
    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("أعطني اقتراحات")

    assert result["status"] == "success"
    assert result["text"] == "اقتراح حواري"
    assert orchestrator.calls == []


def test_dialogue_history_summary_is_bounded_and_survives_prompt_window(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    replies = iter(["اقتراح أول محدد", "اقتراح ثان محدد", "اقتراح ثالث محدد"])
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {
            "status": "success",
            "text": next(replies),
        },
    )
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    manager.process("أعطني اقتراحات")
    manager.process("ماذا أيضًا؟")
    manager.process("أعطني اقتراحات أكثر")

    # Each successful targetless suggestion is dialogue, not an executable
    # project proposal; all three exchanges must survive before recall starts.
    assert [
        item.get("assistant") for item in memory.state.exchange_archive
    ] == ["اقتراح أول محدد", "اقتراح ثان محدد", "اقتراح ثالث محدد"]
    assert all(
        item.get("context_kind") == "dialogue"
        for item in memory.state.exchange_archive
    )

    def unexpected_gateway(*_args, **_kwargs):
        raise AssertionError("summary recall must not call the language provider")

    monkeypatch.setattr(manager_module, "gateway_ask", unexpected_gateway)
    result = manager.process("ماذا كنا نقول قبل قليل في الردود السابقة؟")
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "summary"
    assert "اقتراح أول محدد" in result["text"]
    assert "اقتراح ثان محدد" in result["text"]
    assert "اقتراح ثالث محدد" in result["text"]
    assert result["text"].startswith("ملخص موثّق للحوار المسجّل:")
    assert not result["text"].startswith("نص الحوار المسجل:")
    assert len(result["dialogue_turns"]) <= 6

def test_phase_continuation_stays_on_active_explanation_instead_of_session_restore():
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    result = manager.process(
        "تابع إلى المرحلة الثانية، مع عدم تكرار ما شرحته في المرحلة الأولى"
    )

    assert result["status"] == "success"
    assert result["intent"] == Intent.CYBER_EXPLAIN
    assert result["target"] == "SQL Injection"
    assert result["intent"] != Intent.SESSION_RESTORE


def test_previous_message_question_is_dialogue_history_not_agent_flow():
    parsed = parse("ما الموضوع الذي كنا نشرحه في رسالتي السابقة؟")
    assert parsed["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert parsed["intent"] == Intent.PERSONAL_CHAT


def test_history_recall_keeps_relevant_execution_exchange():
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    sid = memory.state.session_id
    memory.state.add_turn(
        role="user", content="اشرح SQL Injection", target="SQL Injection",
        intent="cyber_explain",
    )
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "اشرح SQL Injection",
            "assistant": "شرح التنفيذ المرتبط بالموضوع",
            "target": "SQL Injection",
            "intent": "cyber_explain",
            "context_kind": "execution",
            "conversation_domain": "technical",
        },
    ]
    result = ConversationManager(orchestrator, memory).process(
        "ما الموضوع الذي كنا نشرحه في رسالتي السابقة؟"
    )
    assert result["source"] == "dialogue_memory"
    assert "شرح التنفيذ المرتبط بالموضوع" in result["text"]


def test_dialogue_prompt_excludes_actual_execution_but_keeps_technical_explanation():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    sid = memory.state.session_id
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "اشرح SQL Injection",
            "assistant": "شرح تقني تعليمي محفوظ",
            "target": "SQL Injection",
            "context_kind": "execution",
            "conversation_domain": "technical",
            "context_transition": "explicit_switch",
        },
        {
            "session_id": sid,
            "user": "أمر تشغيل خاص",
            "assistant": "مخرجات تنفيذ سرية",
            "context_kind": "execution",
            "conversation_domain": "execution",
            "context_transition": "continue",
        },
    ]
    manager = ConversationManager(orchestrator, memory)

    history = manager._history_for_transition(
        ContextTransition.CONTINUE,
        {"conversation_act": "CONVERSATION_CONTINUATION"},
    )
    rendered = " ".join(
        str(turn.get("content") or "")
        for turn in history
    )

    assert "شرح تقني تعليمي محفوظ" in rendered
    assert "مخرجات تنفيذ سرية" not in rendered
    assert orchestrator.calls == []


def test_independent_topic_does_not_send_previous_branch_secret_to_privacy_boundary(monkeypatch):
    import lab_v4_dev.core.orchestrator as orchestrator_module
    from lab_v4_dev.dni.privacy_engine import PrivacyEngine

    secret = "DNI_RUNTIME_TEST_SECRET_OLD_BRANCH_ABC123"
    outbound = []

    def fake_ask(prompt, system=None, **_kwargs):
        outbound.append((str(prompt or ""), str(system or "")))
        if len(outbound) == 1:
            return {"status": "success", "text": f"وصلنا إلى هذه النقطة: {secret}"}
        return {"status": "success", "text": "بدأ شرح CSRF بصورة مستقلة."}

    monkeypatch.setattr(orchestrator_module, "ask", fake_ask)
    monkeypatch.setattr("lab_v4_dev.intent.response_cache.get", lambda *_args: None)
    monkeypatch.setattr(
        "lab_v4_dev.awareness.knowledge_base.search",
        lambda *_args, **_kwargs: None,
    )

    context = ContextStore()
    agent = type("Agent", (), {"db": None})()
    orchestrator = Orchestrator(agent, context)
    memory = DialogueMemory(context)
    manager = ConversationManager(orchestrator, memory)

    first = manager.process("اشرح SQL Injection")
    second = manager.process(
        "اشرح CSRF بالتفصيل، وابدأ شرحًا مستقلًا عن الموضوع السابق"
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    prompt, system = outbound[-1]
    assert secret not in prompt
    assert secret not in system
    assert PrivacyEngine().inspect(prompt)["allow_external"] is True
    assert PrivacyEngine().inspect(system)["allow_external"] is True


def test_return_to_main_topic_without_history_is_classified_and_safe():
    parsed = parse("ارجع للموضوع الرئيسي")
    assert parsed["conversation_act"] == "TOPIC_RETURN"

    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))
    result = manager.process("ارجع للموضوع الرئيسي")

    assert result["status"] == "needs_clarification"
    assert orchestrator.calls == []


def test_restoring_named_topic_does_not_merge_the_intervening_branch():
    sid = "dialogue-branch-regression"
    exchanges = [
        {
            "session_id": sid, "user": "اشرح SQL Injection",
            "assistant": "شرح SQL Injection", "target": "SQL Injection",
            "context_kind": "dialogue", "conversation_domain": "technical",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid, "user": "كيف تحدث؟",
            "assistant": "تفصيل SQL Injection", "target": "SQL Injection",
            "context_kind": "dialogue", "conversation_domain": "technical",
            "context_transition": "continue",
        },
        {
            "session_id": sid, "user": "اشرح CSRF",
            "assistant": "شرح CSRF", "target": "CSRF",
            "context_kind": "dialogue", "conversation_domain": "technical",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid, "user": "كيف تعمل؟",
            "assistant": "تفصيل CSRF", "target": "CSRF",
            "context_kind": "dialogue", "conversation_domain": "technical",
            "context_transition": "continue",
        },
        {
            "session_id": sid, "user": "ارجع إلى SQL Injection",
            "assistant": "عدنا إلى SQL Injection", "target": "SQL Injection",
            "context_kind": "dialogue", "conversation_domain": "technical",
            "context_transition": "restore",
        },
    ]

    branch = ConversationManager._latest_dialogue_branch(exchanges)

    assert [item["user"] for item in branch] == [
        "اشرح SQL Injection",
        "كيف تحدث؟",
    ]
    assert all("CSRF" not in item["user"] for item in branch)
    assert all("CSRF" not in item["assistant"] for item in branch)


def test_summary_since_beginning_includes_distinct_topics_in_chronological_order():
    orchestrator = CapturingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    sid = memory.state.session_id
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "أشعر أن الذكاء الاصطناعي يتطور بسرعة ولا أعرف ماذا أتعلم.",
            "assistant": "ابدأ بتجربة أداة ذكاء اصطناعي واحدة على مهمة يومية.",
            "target": None,
            "context_kind": "dialogue",
            "conversation_domain": "social",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "ما الفرق بين القائمة والقاموس في Python؟",
            "assistant": "القائمة تحفظ عناصر متسلسلة والقاموس يربط المفاتيح بالقيم.",
            "target": "list و dict في Python",
            "context_kind": "execution",
            "conversation_domain": "technical",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "نرجع لموضوع تعلم استخدام أدوات الذكاء الاصطناعي.",
            "assistant": "ابدأ بتجربة أداة واحدة على مهمة حقيقية.",
            "target": None,
            "context_kind": "dialogue",
            "conversation_domain": "social",
            "context_transition": "restore",
        },
    ]
    manager = ConversationManager(orchestrator, memory)

    result = manager._answer_dialogue_history(
        "لخص الحوار منذ البداية واذكر الموضوعين اللذين ناقشناهما بالترتيب",
        "summary",
        memory.state.exchange_archive,
    )

    assert result["status"] == "success"
    assert "الذكاء الاصطناعي يتطور بسرعة" in result["text"]
    assert "القائمة والقاموس في Python" in result["text"]
    assert result["text"].index("الذكاء الاصطناعي يتطور بسرعة") < result["text"].index(
        "القائمة والقاموس في Python"
    )


def test_gateway_error_does_not_guess_that_connectivity_is_the_cause(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {
            "status": "error",
            "text": "",
            "error": {
                "code": "NO_PROVIDER_AVAILABLE",
                "message": "No configured provider is available",
            },
            "provider_chain": [],
        },
    )
    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager._handle_chat(
        "أكمل من حيث توقفنا في موضوع تعلم استخدام أدوات الذكاء الاصطناعي.",
        "CHAT",
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "target": "",
            "conversation_domain": "general",
            "conversation_act": "CONVERSATION_CONTINUATION",
            "response_attributes": {},
        },
        user_question="أكمل من حيث توقفنا في موضوع تعلم استخدام أدوات الذكاء الاصطناعي.",
        history=[],
    )

    assert result["status"] == "error"
    assert result["gateway_error"]["code"] == "NO_PROVIDER_AVAILABLE"
    assert "لا يوجد حاليًا مزود" in result["text"]
    assert "تحقق من الاتصال" not in result["text"]
