from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **_kwargs):
        self.calls.append((text, dict(parsed or {})))
        return {"status": "success", "intent": (parsed or {}).get("intent"), "text": "تم"}


def _manager(monkeypatch):
    monkeypatch.setattr(conversation_module, "gateway_ask", lambda *_a, **_k: {
        "status": "success", "text": "إجابة محادثية.", "provider_used": "offline-test",
    })
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(ContextStore())
    return ConversationManager(orchestrator, memory), memory, orchestrator


def test_explicit_independent_marker_does_not_require_parsed_target():
    assert ConversationManager._is_explicit_independent_topic(
        "اشرح CSRF بالتفصيل، موضوع مستقل عن السابق",
        {"target": ""},
    )


def test_return_without_previous_topic_is_explicit_and_safe(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    result = manager.process("ارجع للموضوع الرئيسي")
    assert result["semantic_request"]["conversation_act"] == "TOPIC_RETURN"
    assert result["semantic_request"]["context_transition"] == "ambiguous"
    assert result["semantic_request"]["target"] in ("", None)
    assert memory.last_topic in ("", None)
    assert orchestrator.calls == []


def test_named_return_and_continuation_preserve_separate_branches(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")
    manager.process("اشرح CSRF")
    named = manager.process("ارجع لشرح SQL Injection")
    assert named["semantic_request"]["conversation_act"] == "TOPIC_RETURN"
    assert named["semantic_request"]["target"] == "SQL Injection"
    assert memory.last_topic == "SQL Injection"
    assert memory.previous_context_entity()["entity"] == "CSRF"

    continued = manager.process("اكمل الشرح")
    assert continued["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert continued["semantic_request"]["target"] == "SQL Injection"
    assert len(orchestrator.calls) == 4


def test_explicit_dialogue_topic_creates_a_separate_branch(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")

    result = manager.process("دعنا نتحدث عن مفهوم الشبكات")

    assert result["status"] == "success"
    assert result["semantic_request"]["target"] == "الشبكات"
    assert result["semantic_request"]["context_transition"] == "explicit_switch"
    assert memory.last_topic == "الشبكات"
    assert len(orchestrator.calls) == 1


def test_provider_failure_records_user_topic_but_not_failed_answer(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    monkeypatch.setattr(conversation_module, "gateway_ask", lambda *_a, **_k: {
        "status": "error",
        "text": "PROVIDER_FAILURE_SENTINEL",
        "error": {"code": "PROVIDER_UNAVAILABLE"},
    })

    manager.process("اشرح SQL Injection")
    manager.process("دعنا نتحدث عن مفهوم الشبكات")

    assert memory.last_topic == "الشبكات"
    network_user_turns = [
        turn for turn in memory.state.history
        if turn.get("role") == "user" and turn.get("target") == "الشبكات"
    ]
    assert network_user_turns
    assert not any(
        turn.get("role") == "assistant"
        and "PROVIDER_FAILURE_SENTINEL" in turn.get("content", "")
        for turn in memory.state.history
    )
    assert not any(
        item.get("target") == "الشبكات"
        for item in memory.state.exchange_archive
    )


def test_return_to_main_topic_works_after_new_topic_provider_failure(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    monkeypatch.setattr(conversation_module, "gateway_ask", lambda *_a, **_k: {
        "status": "error",
        "text": "تعذر الوصول إلى النموذج",
        "error": {"code": "PROVIDER_UNAVAILABLE"},
    })

    manager.process("اشرح SQL Injection")
    manager.process("دعنا نتحدث عن مفهوم الشبكات")
    result = manager.process("ارجع للموضوع الرئيسي")

    assert result["semantic_request"]["conversation_act"] == "TOPIC_RETURN"
    assert result["semantic_request"]["target"] == "SQL Injection"
    assert memory.last_topic == "SQL Injection"
    assert orchestrator.calls[-1][1]["target"] == "SQL Injection"


def test_stop_working_is_a_local_control_not_an_unsupported_task(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)

    result = manager.process("توقف عن العمل")

    assert result["status"] == "success"
    assert result["intent"] == "stop"
    assert result["executed"] is False
    assert orchestrator.calls == []



def test_new_dialogue_topic_does_not_receive_previous_branch_content(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    secret = "OLD_SQL_BRANCH_PRIVATE_SENTINEL"
    memory.state.last_topic = "SQL Injection"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"
    memory.state.exchange_archive = [{
        "user": "اشرح SQL Injection",
        "assistant": f"نقطة توقف خاصة: {secret}",
        "intent": "cyber_explain",
        "target": "SQL Injection",
        "conversation_domain": "technical",
        "conversation_act": "NONE",
        "context_kind": "dialogue",
    }]
    outbound = []

    def capture_gateway(prompt, system=None, **_kwargs):
        outbound.append((str(prompt or ""), str(system or "")))
        return {"status": "success", "text": "لنبدأ موضوع الشبكات."}

    monkeypatch.setattr(conversation_module, "gateway_ask", capture_gateway)
    result = manager.process("دعنا نتحدث عن مفهوم الشبكات")

    assert result["status"] == "success"
    assert outbound
    assert secret not in outbound[-1][0]
    assert secret not in outbound[-1][1]
    assert result["semantic_request"]["context_transition"] == "explicit_switch"



def test_continue_after_provider_failure_stays_on_active_new_topic(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    secret = "PREVIOUS_SQL_BRANCH_SENTINEL"
    memory.state.last_topic = "SQL Injection"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"
    memory.state.exchange_archive = [{
        "user": "اشرح SQL Injection",
        "assistant": secret,
        "intent": "cyber_explain",
        "target": "SQL Injection",
        "conversation_domain": "technical",
        "conversation_act": "NONE",
        "context_kind": "dialogue",
    }]
    monkeypatch.setattr(conversation_module, "gateway_ask", lambda *_a, **_k: {
        "status": "error",
        "text": "تعذر الوصول إلى النموذج",
        "error": {"code": "PROVIDER_UNAVAILABLE"},
    })
    manager.process("دعنا نتحدث عن مفهوم الشبكات")

    outbound = []

    def capture_gateway(prompt, system=None, **_kwargs):
        outbound.append((str(prompt or ""), str(system or "")))
        return {"status": "success", "text": "لنواصل موضوع الشبكات."}

    monkeypatch.setattr(conversation_module, "gateway_ask", capture_gateway)
    result = manager.process("اكمل الموضوع")

    assert result["status"] == "success"
    assert result["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert result["semantic_request"]["target"] == "الشبكات"
    assert memory.last_topic == "الشبكات"
    assert outbound
    assert secret not in outbound[-1][0]
    assert secret not in outbound[-1][1]
    assert len(orchestrator.calls) == 0



def test_bare_no_without_pending_confirmation_preserves_active_topic(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")

    result = manager.process("لا")

    active = memory.active_context_entity()
    assert result["status"] == "success"
    assert memory.last_topic == "SQL Injection"
    assert active is not None
    assert active["entity"] == "SQL Injection"
    assert active["action"] == "cyber_explain"
    assert len(orchestrator.calls) == 1



def test_recall_question_about_prior_topic_uses_dialogue_memory(monkeypatch):
    from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics

    utterance = "هل تتذكر موضوع فن النقش البارز الذي تحدثنا فيه"
    signal = classify_conversation_semantics(utterance)
    assert signal["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert signal["response_attributes"]["dialogue_response_mode"] == "answer"

    manager, memory, orchestrator = _manager(monkeypatch)
    memory.state.exchange_archive = [{
        "user": "تحدثنا عن فن النقش البارز في اللوحة.",
        "assistant": "ناقشنا بروز الشكل والظلال وتباين الألوان.",
        "target": "فن النقش البارز",
        "intent": "personal_chat",
        "conversation_domain": "general",
        "conversation_act": "CASUAL_CONVERSATION",
        "context_kind": "dialogue",
    }]

    result = manager.process(utterance)

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert "فن النقش البارز" in result["text"]
    assert orchestrator.calls == []


def test_recall_question_without_saved_topic_is_honest_not_unsupported(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)

    result = manager.process("هل تتذكر موضوع فن النقش البارز الذي تحدثنا فيه")

    assert result["status"] == "needs_clarification"
    assert result["source"] == "dialogue_memory"
    assert "لا يوجد سجل حوار كافٍ" in result["text"]
    assert orchestrator.calls == []


def test_explicit_explanation_starts_fresh_even_when_same_topic_is_stale(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    memory.state.last_topic = "SQL Injection"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"

    result = manager.process(
        "اشرح SQL Injection بالتفصيل، وتوقف عند نقطة واضحة"
    )

    assert result["status"] == "success"
    assert result["semantic_request"]["context_transition"] == "explicit_switch"
    assert result["semantic_request"]["target"] == "SQL Injection"
    assert orchestrator.calls[-1][1]["target"] == "SQL Injection"


def test_dialogue_summary_is_grounded_and_does_not_call_provider(monkeypatch):
    manager, _memory, _orchestrator = _manager(monkeypatch)

    def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("history summary must not call the language provider")

    monkeypatch.setattr(conversation_module, "gateway_ask", forbidden_provider)
    exchanges = [{
        "user": "اشرح SQL Injection",
        "assistant": "توقفنا عند الفرق بين الاستعلام المباشر والاستعلام المعلّم.",
        "target": "SQL Injection",
        "intent": "cyber_explain",
        "conversation_domain": "technical",
        "conversation_act": "NONE",
        "context_kind": "dialogue",
    }]

    result = manager._answer_dialogue_history(
        "استرجع سياق الجلسة الحالية", "summary", exchanges
    )

    assert result["status"] == "success"
    assert "SQL Injection" in result["text"]
    assert "الاستعلام المعلّم" in result["text"]
    assert "محاولة اختراق المشروع" not in result["text"]


def test_topic_recall_uses_saved_exchange_without_provider(monkeypatch):
    manager, _memory, _orchestrator = _manager(monkeypatch)

    def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("topic recall must use the saved exchange")

    monkeypatch.setattr(conversation_module, "gateway_ask", forbidden_provider)
    exchanges = [{
        "user": "تحدثنا عن فن النقش البارز في اللوحة.",
        "assistant": "ناقشنا بروز الشكل والظلال وتباين الألوان.",
        "target": "فن النقش البارز",
        "intent": "personal_chat",
        "conversation_domain": "general",
        "conversation_act": "CASUAL_CONVERSATION",
        "context_kind": "dialogue",
    }]

    result = manager._answer_dialogue_history(
        "هل تتذكر موضوع فن النقش البارز الذي تحدثنا فيه",
        "answer",
        exchanges,
    )

    assert result["status"] == "success"
    assert "فن النقش البارز" in result["text"]
    assert "بروز الشكل والظلال" in result["text"]


def test_bare_verify_asks_for_a_target_instead_of_becoming_unsupported(monkeypatch):
    manager, _memory, orchestrator = _manager(monkeypatch)

    result = manager.process("تحقق")

    assert result["status"] == "needs_clarification"
    assert getattr(result["intent"], "value", result["intent"]) == "verify_fix"
    assert "ما الذي تريدني أن أتحقق منه" in result["text"]
    assert orchestrator.calls == []


def test_provider_failure_does_not_offer_to_save_missing_explanation(monkeypatch):
    from lab_v4_dev.core import orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.intent.intents import Intent

    monkeypatch.setattr(
        orchestrator_module,
        "ask",
        lambda *_args, **_kwargs: {
            "status": "error",
            "error": {"code": "PROVIDER_UNAVAILABLE"},
        },
    )
    monkeypatch.setattr(
        "lab_v4_dev.llm.prompt_builder.build_cybersec_prompt",
        lambda *_args, **_kwargs: ("system", "prompt"),
    )
    instance = Orchestrator.__new__(Orchestrator)
    instance.context = ContextStore()

    result = instance._route(
        Intent.CYBER_EXPLAIN,
        "SQL Injection",
        "general",
        "اشرح SQL Injection",
        response_attributes={"dialogue_response_mode": "answer"},
        context_transition="new_independent",
    )

    assert result["status"] == "error"
    assert result["pending_save"] is None
    assert result["pending_confirmation"] is None
    assert result["save_prompt"] is None
    assert "مزود اللغة" in result["text"]


def test_privacy_block_is_not_reported_as_provider_outage(monkeypatch):
    from lab_v4_dev.core import orchestrator as orchestrator_module
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.intent.intents import Intent

    monkeypatch.setattr(
        orchestrator_module,
        "ask",
        lambda *_args, **_kwargs: {
            "status": "error",
            "error": {"code": "PRIVACY_EXTERNAL_BLOCKED"},
        },
    )
    monkeypatch.setattr(
        "lab_v4_dev.llm.prompt_builder.build_cybersec_prompt",
        lambda *_args, **_kwargs: ("system", "prompt"),
    )
    instance = Orchestrator.__new__(Orchestrator)
    instance.context = ContextStore()

    result = instance._route(
        Intent.CYBER_EXPLAIN,
        "SQL Injection",
        "general",
        "اشرح SQL Injection",
        response_attributes={"dialogue_response_mode": "answer"},
        context_transition="new_independent",
    )

    assert result["status"] == "error"
    assert "بوابة الخصوصية" in result["text"]
    assert "مزود اللغة" not in result["text"]
    assert result["save_prompt"] is None

def test_natural_language_friendly_start_creates_a_fresh_dialogue_session(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")
    previous_session_id = memory.state.session_id
    prior_execution_calls = len(orchestrator.calls)

    result = manager.process("قلت نبدا حوار ودي جديد مثلا")

    assert result["status"] == "success"
    assert result["source"] == "conversation_manager"
    assert "جلسة حوار جديدة ومستقلة" in result["text"]
    assert memory.state.session_id != previous_session_id
    assert memory.state.history == []
    assert memory.state.exchange_archive == []
    assert len(orchestrator.calls) == prior_execution_calls


def test_offline_continuation_after_social_only_turns_does_not_echo_greeting_archive(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    monkeypatch.setattr(conversation_module, "gateway_ask", lambda *_a, **_k: {
        "status": "error",
        "text": "",
        "error": {"code": "NO_PROVIDER_AVAILABLE"},
    })

    opener = manager.process("لنتحدث قليلا")
    state_question = manager.process("كيف الحال")
    result = manager.process("اكمل")

    assert opener["status"] == "success"
    assert state_question["status"] == "success"
    assert result["status"] == "success"
    assert result["source"] == "local_dialogue_fallback"
    assert result["recovery"] == "provider_unavailable_local_dialogue"
    assert "لم نحدد موضوعًا" in result["text"]
    assert "آخر نقطة محفوظة في هذا الفرع" not in result["text"]
    assert "أنا بخير، شكرًا لسؤالك" not in result["text"]
    assert "كيف الحال" not in result["text"]
    assert orchestrator.calls == []


def test_social_only_dialogue_summary_does_not_present_greetings_as_a_topic(monkeypatch):
    manager, memory, _orchestrator = _manager(monkeypatch)
    exchanges = [
        {
            "user": "لنتحدث قليلا",
            "assistant": "يمكننا اختيار موضوع خفيف ثم تطوير النقاش بحسب ما يثير اهتمامك.",
            "conversation_domain": "social",
            "context_kind": "social",
            "session_id": memory.state.session_id,
        },
        {
            "user": "كيف الحال",
            "assistant": "أنا بخير، شكرًا لسؤالك. كيف حالك أنت؟",
            "conversation_domain": "social",
            "context_kind": "social",
            "session_id": memory.state.session_id,
        },
    ]

    result = manager._answer_dialogue_history("ماذا كنا نقول", "summary", exchanges)

    assert result["status"] == "success"
    assert "لم نحدد موضوعًا فعليًا للنقاش بعد" in result["text"]
    assert "أنا بخير، شكرًا لسؤالك" not in result["text"]
    assert "لنتحدث قليلا" not in result["text"]

def test_fragmentary_messages_do_not_inherit_or_mutate_the_active_dialogue(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    manager.process("اشرح SQL Injection")

    previous_topic = memory.state.last_topic
    previous_session_id = memory.state.session_id
    previous_history = [dict(turn) for turn in memory.state.history]
    previous_archive = [dict(item) for item in memory.state.exchange_archive]
    previous_calls = len(orchestrator.calls)

    for fragment in ("ظ", "م", "ث", "تز"):
        result = manager.process(fragment)
        assert result["status"] == "needs_clarification"
        assert result["source"] == "conversation_manager"
        assert result["executed"] is False
        assert "مبتورة" in result["text"]
        assert memory.state.last_topic == previous_topic
        assert memory.state.session_id == previous_session_id
        assert memory.state.history == previous_history
        assert memory.state.exchange_archive == previous_archive
        assert len(orchestrator.calls) == previous_calls


def test_fragment_guard_keeps_valid_short_arabic_words():
    assert ConversationManager._is_fragmentary_turn("ظ")
    assert ConversationManager._is_fragmentary_turn("تز")
    assert not ConversationManager._is_fragmentary_turn("لا")
    assert not ConversationManager._is_fragmentary_turn("من")
    assert not ConversationManager._is_fragmentary_turn("هل")

