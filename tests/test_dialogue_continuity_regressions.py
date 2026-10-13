from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics


class RecordingOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {
            "status": "success",
            "intent": (parsed or {}).get("intent"),
            "text": "رد التنفيذ",
        }


def _manager(monkeypatch):
    calls = []

    def fake_gateway(prompt, **kwargs):
        calls.append((prompt, kwargs))
        if "طلب المستخدم الحالي: اكتب ملخص" in prompt or "ماذا كنا نقول" in prompt:
            answer = "ملخص: بدأ الحوار بموضوع عام، ثم طلب المستخدم الاستمرار في السياق نفسه."
        else:
            answer = f"رد حواري رقم {len(calls)}"
        return {"status": "success", "text": answer, "provider_used": "test"}

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        fake_gateway,
    )
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    return ConversationManager(orchestrator, memory), memory, orchestrator, calls


def test_same_dialogue_continuation_does_not_become_work_resume_clarification(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)

    first = manager.process("ماذا تستطيع فعله؟")
    assert first["status"] == "success"
    assert memory.active_context_entity() is None

    continued = manager.process("نعم نكمل في نفس سياق الموضوع")

    assert continued["status"] == "success"
    assert continued["source"] != "conversation_manager"
    assert "استكمال الحوار السابق أم استكمال العمل" not in continued.get("text", "")
    assert len(calls) == 2
    assert "رد حواري رقم 1" in calls[-1][0]
    assert orchestrator.calls == []


def test_dialogue_summary_request_returns_summary_not_transcript(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    manager.process("ماذا تستطيع فعله؟")
    result = manager.process("اكتب ملخص حوار الجلسة")

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "summary"
    assert result["text"].startswith("ملخص الحوار الحالي:")
    assert len(result["text"]) < 700
    assert "المستخدم:" not in result["text"]
    assert "الوكيل:" not in result["text"]
    assert "المستخدم:" not in result["text"]
    assert "الوكيل:" not in result["text"]
    # Summary is rendered directly from the bounded local archive; history recall
    # must not invoke the provider or pass a transcript into an LLM prompt.
    assert len(calls) == 1
    assert orchestrator.calls == []


def test_short_summary_phrase_is_resolved_as_dialogue_history():
    continuation = classify_conversation_semantics("نعم نكمل في نفس سياق الموضوع")
    assert continuation["conversation_act"] == "CONVERSATION_CONTINUATION"

    for text in ("ملخص الحوار", "ملخص حوار الجلسة", "اكتب ملخص الحوار"):
        result = classify_conversation_semantics(text)
        assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
        assert result["response_attributes"]["dialogue_response_mode"] == "summary"


def test_last_question_retrieves_last_user_message_without_dumping_history(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    manager.process("ماذا تستطيع فعله؟")
    result = manager.process("ما آخر سؤال سألتك أنا؟")

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["dialogue_response_mode"] == "last_question"
    assert "ماذا تستطيع فعله؟" in result["text"]
    assert "المستخدم:" not in result["text"]
    assert orchestrator.calls == []


def test_question_about_unsolicited_explanation_is_dialogue_history():
    result = classify_conversation_semantics("من طلب منك هذا الشرح؟")
    assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert result["response_attributes"]["dialogue_response_mode"] == "answer"


def test_explicit_dialogue_continuation_excludes_saved_work_turns(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.add_turn(
        role="user",
        content="استكمل العمل في الملف secret.py",
        context_kind="work",
        conversation_domain="work",
    )
    memory.state.add_turn(
        role="assistant",
        content="تفاصيل عمل لا يجب إدخالها في الحوار العام",
        context_kind="work",
        conversation_domain="work",
    )
    manager.process("ماذا تستطيع فعله؟")
    result = manager.process("نعم نكمل في نفس سياق الموضوع")

    assert result["status"] == "success"
    assert len(calls) == 2
    assert "تفاصيل عمل لا يجب إدخالها" not in calls[-1][0]
    assert "secret.py" not in calls[-1][0]

def test_topic_restore_uses_archived_exchange_after_turn_window_rolls_over():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    # The bounded turn list now contains only a different, newer branch.
    for role in ("user", "assistant") * 4:
        memory.state.add_turn(
            role=role,
            content="محتوى أحدث لا يخص اللوحة",
            target="موضوع أحدث",
            intent="cyber_explain",
            conversation_domain="technical",
            context_kind="dialogue",
        )

    memory.state.exchange_archive = [
        {
            "session_id": memory.state.session_id,
            "user": "استخدمت الذهب والبيج والأزرق الداكن في اللوحة",
            "assistant": "هذه الألوان تخلق تباينًا بين الدفء والبرودة.",
            "target": "اللوحة الفنية",
            "intent": "personal_chat",
            "conversation_domain": "general",
            "context_kind": "dialogue",
        },
        {
            "session_id": memory.state.session_id,
            "user": "تفاصيل عمل سرية",
            "assistant": "رد عمل سري",
            "target": "اللوحة الفنية",
            "intent": "modify_file",
            "conversation_domain": "work",
            "context_kind": "work",
        },
    ]

    restored = manager._history_for_transition(
        ContextTransition.RESTORE,
        {"target": "اللوحة الفنية"},
    )
    text = " ".join(turn["content"] for turn in restored)

    assert "الذهب والبيج والأزرق الداكن" in text
    assert "تخلق تباينًا" in text
    assert "تفاصيل عمل سرية" not in text
    assert "رد عمل سري" not in text


def test_new_session_resets_dialogue_memory_even_without_orchestrator_reset_hook(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.last_topic = "موضوع قديم"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.exchange_archive = [{
        "user": "معلومة قديمة",
        "assistant": "رد قديم",
        "context_kind": "dialogue",
        "conversation_domain": "general",
    }]

    result = manager.process("جلسة جديدة")

    assert result["status"] == "success"
    assert memory.state.last_topic is None
    assert memory.state.exchange_archive == []


def test_natural_language_new_dialogue_request_resets_before_pending_clarification(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.last_topic = "CSRF"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.exchange_archive = [{
        "user": "اشرح CSRF",
        "assistant": "شرح قديم",
        "context_kind": "dialogue",
        "conversation_domain": "technical",
        "session_id": memory.state.session_id,
    }]
    memory.state.pending_clarification = {"kind": "project_order", "request": "قائمة الملفات"}
    old_session_id = memory.state.session_id

    result = manager.process("أريد بدء جلسة حوار جديدة ومستقلة تمامًا عن الحوار السابق. لا تستعد سياقه ولا تخلط بينهما.")

    assert result["status"] == "success"
    assert memory.state.last_topic is None
    assert memory.state.exchange_archive == []
    assert memory.state.pending_clarification is None
    assert memory.state.session_id != old_session_id


def test_dialogue_history_recall_excludes_exchanges_from_other_session(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.exchange_archive = [
        {
            "user": "اشرح CSRF",
            "assistant": "شرح من جلسة أخرى",
            "target": "CSRF",
            "context_kind": "dialogue",
            "conversation_domain": "technical",
            "session_id": "old-session-id",
        }
    ]

    result = manager._answer_dialogue_history("ماذا تتذكر عن حوارنا الحالي؟", "summary", memory.state.exchange_archive)

    assert result["status"] == "needs_clarification"
    assert "CSRF" not in result["text"]
    assert "جلسة أخرى" not in result["text"]


def test_social_dialogue_never_exposes_technical_save_prompt(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    manager._dispatch = lambda *args, **kwargs: {
        "status": "success",
        "intent": "personal_chat",
        "text": "رد حواري",
        "save_prompt": "هل تحفظ هذا الشرح؟",
        "pending_save": "موضوع تقني",
        "pending_confirmation": {"kind": "save_kb", "topic": "موضوع تقني"},
    }

    result = manager.process("السلام عليكم")

    assert result["status"] == "success"
    assert "save_prompt" not in result
    assert "pending_save" not in result
    assert "pending_confirmation" not in result


def test_restore_snapshot_drops_turns_and_exchanges_from_foreign_session():
    memory = DialogueMemory(object())
    restored = memory.restore_snapshot({
        "session_id": "current-session",
        "history": [
            {"role": "user", "content": "رسالة حالية", "session_id": "current-session"},
            {"role": "assistant", "content": "تسرب قديم", "session_id": "old-session"},
        ],
        "exchange_archive": [
            {"user": "موضوع حالي", "assistant": "رد حالي", "session_id": "current-session"},
            {"user": "CSRF قديم", "assistant": "شرح قديم", "session_id": "old-session"},
        ],
    })

    assert restored is True
    assert memory.state.session_id == "current-session"
    assert [turn["content"] for turn in memory.state.history] == ["رسالة حالية"]
    assert [item["user"] for item in memory.state.exchange_archive] == ["موضوع حالي"]


def test_prompt_history_excludes_foreign_session_exchanges():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    memory.state.exchange_archive = [
        {
            "user": "حوار الجلسة الحالية",
            "assistant": "رد حالي",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "session_id": memory.state.session_id,
        },
        {
            "user": "CSRF من جلسة أخرى",
            "assistant": "شرح قديم",
            "context_kind": "dialogue",
            "conversation_domain": "technical",
            "session_id": "old-session-id",
        },
    ]

    history = manager._history_for_transition(
        ContextTransition.CONTINUE,
        {"conversation_act": "CONVERSATION_CONTINUATION"},
    )
    text = " ".join(turn["content"] for turn in history)

    assert "حوار الجلسة الحالية" in text
    assert "CSRF" not in text
    assert "شرح قديم" not in text


def test_casual_darija_opener_does_not_inherit_active_technical_topic(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.last_topic = "CSRF"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"

    result = manager.process("بغيت نهضر معاك على شي موضوع خفيف، كيفاش داز نهارك؟")

    assert result["status"] == "success"
    assert result["source"] == "local_social"
    assert "نهارك" in result["text"]
    assert "CSRF" not in result["text"]
    assert result["semantic_request"]["target"] is None
    assert result["semantic_request"]["conversation_domain"] == "social"
    assert len(orchestrator.calls) == 0

def test_targetless_general_continuation_uses_recent_dialogue_archive():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    memory.state.exchange_archive = [
        {
            "session_id": memory.state.session_id,
            "user": "صنعت لوحة بنحت بارز",
            "assistant": "حدثني عن تفاصيلها.",
            "context_kind": "dialogue",
            "conversation_domain": "general",
        },
        {
            "session_id": memory.state.session_id,
            "user": "ألوانها الذهبية والبيج والأزرق الداكن",
            "assistant": "هذه الألوان تخلق تباينًا.",
            "context_kind": "dialogue",
            "conversation_domain": "general",
        },
        {
            "session_id": memory.state.session_id,
            "user": "تفاصيل عمل",
            "assistant": "محتوى عمل",
            "context_kind": "work",
            "conversation_domain": "work",
        },
    ]

    restored = manager._history_for_transition(
        ContextTransition.CONTINUE,
        {"conversation_act": "CONVERSATION_CONTINUATION"},
    )
    text = " ".join(turn["content"] for turn in restored)

    assert "نحت بارز" in text
    assert "الأزرق الداكن" in text
    assert "محتوى عمل" not in text



def test_direct_request_for_discussion_topic_gets_a_topic_without_clarification(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)

    result = manager.process("انت اعطيني اقتراحات")

    assert result["status"] == "success"
    assert result["source"] == "local_social"
    assert "شنو رأيك؟" in result["text"]
    assert "تحتاجها" not in result["text"]
    assert orchestrator.calls == []


def test_restore_snapshot_rejects_untagged_legacy_turns_and_exchanges():
    memory = DialogueMemory(object())
    restored = memory.restore_snapshot({
        "session_id": "active-session",
        "history": [
            {"role": "user", "content": "CSRF من سجل قديم"},
            {"role": "assistant", "content": "شرح تقني قديم"},
            {"role": "user", "content": "رسالة هذه الجلسة", "session_id": "active-session"},
        ],
        "exchange_archive": [
            {"user": "CSRF قديم", "assistant": "شرح قديم"},
            {"user": "حوار حالي", "assistant": "رد حالي", "session_id": "active-session"},
        ],
    })

    assert restored is True
    assert [turn["content"] for turn in memory.state.history] == ["رسالة هذه الجلسة"]
    assert [item["user"] for item in memory.state.exchange_archive] == ["حوار حالي"]
