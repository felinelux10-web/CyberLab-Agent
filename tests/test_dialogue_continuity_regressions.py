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


def test_local_social_and_dialogue_recall_share_response_finalization(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)

    class RecordingDNI:
        def __init__(self):
            self.analyses = []

        def set_conversation_analysis(self, analysis):
            self.analyses.append(dict(analysis))

    dni = RecordingDNI()
    manager.dni = dni
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.format_response",
        lambda text, mode: f"FINALIZED::{text}",
    )

    social = manager.process(
        "بغيت نهضر معاك على شي موضوع خفيف، كيفاش داز نهارك؟"
    )

    assert social["status"] == "success"
    assert social["source"] == "local_social"
    assert social["text"].startswith("FINALIZED::")
    assert memory.state.history[-1]["role"] == "assistant"
    assert memory.state.history[-1]["content"] == social["text"]
    assert len(dni.analyses) == 1
    assert dni.analyses[-1]["conversation_domain"] == "social"

    recalled = manager.process("اكتب ملخص حوار الجلسة")

    assert recalled["status"] == "success"
    assert recalled["source"] == "dialogue_memory"
    assert recalled["text"].startswith("FINALIZED::")
    assert memory.state.history[-1]["content"] == recalled["text"]
    assert len(dni.analyses) == 2
    assert orchestrator.calls == []


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
            "context_transition": "new_independent",
        },
        {
            "session_id": memory.state.session_id,
            "user": "ألوانها الذهبية والبيج والأزرق الداكن",
            "assistant": "هذه الألوان تخلق تباينًا.",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "continue",
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



def test_darija_misspellings_requesting_a_topic_are_handled_as_social_chat(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)

    for text in ("نت قتارح شي موضوع", "عن اي موضوع قتارح نتا"):
        result = manager.process(text)
        assert result["status"] == "success"
        assert result["source"] == "local_social"
        assert "شنو رأيك؟" in result["text"]

    assert orchestrator.calls == []

def test_natural_suggestion_phrases_return_topics_directly(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)

    for text in (
        "اقترح انت بعض المواضيع المثيرة",
        "اريد اقتراحات اخرى في مجال اخر",
    ):
        result = manager.process(text)
        assert result["status"] == "success"
        assert result["source"] == "local_social"
        assert "التكنولوجيا" in result["text"]
        assert "الفن" in result["text"]
        assert "شنو رأيك؟" in result["text"]

    assert orchestrator.calls == []


def test_dialogue_summary_only_describes_latest_branch_and_stopping_point(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.last_topic = "الرسم البارز"
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "كنا نناقش الراحة وتحقيق الأهداف",
            "assistant": "هل الراحة تأتي من الإنجاز أم من الطريق؟",
            "target": None,
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "دعنا ننتقل إلى الرسم البارز",
            "assistant": "يمكننا بحث مزج النقش بالتقنية",
            "target": "الرسم البارز",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "explicit_switch",
        },
        {
            "session_id": sid,
            "user": "أحب الرسم البارز والنقش البارز",
            "assistant": "هل تفضل تطبيقًا فنيًا أم أداة تحول الصور إلى نقش ثلاثي الأبعاد؟",
            "target": "الرسم البارز",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "continue",
        },
    ]

    result = manager._answer_dialogue_history(
        "اكتب ملخص الحوار",
        "summary",
        memory.state.exchange_archive,
    )

    assert result["status"] == "success"
    assert "الرسم البارز" in result["text"]
    assert "نقطة التوقف" in result["text"]
    assert "الراحة وتحقيق الأهداف" not in result["text"]
    assert "هل تفضل تطبيقًا فنيًا" in result["text"]


def test_dialogue_recall_rejects_untagged_exchange_when_session_is_known(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    result = manager._answer_dialogue_history(
        "ماذا كنا نقول؟",
        "summary",
        [{
            "user": "CSRF من أرشيف قديم",
            "assistant": "شرح قديم لا يخص الجلسة الحالية",
            "context_kind": "dialogue",
            "conversation_domain": "technical",
        }],
    )

    assert result["status"] == "needs_clarification"
    assert "CSRF" not in result["text"]
    assert "شرح قديم" not in result["text"]


def test_general_continuation_uses_only_exchanges_after_latest_branch_boundary():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    sid = memory.state.session_id
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "موضوع الفرع الأول",
            "assistant": "رد الفرع الأول",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "بدأنا موضوعًا مختلفًا",
            "assistant": "رد الفرع الثاني",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "explicit_switch",
        },
        {
            "session_id": sid,
            "user": "أكمل النقطة الأخيرة",
            "assistant": "آخر نقطة في الفرع الثاني",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "continue",
        },
    ]

    history = manager._history_for_transition(
        ContextTransition.CONTINUE,
        {"conversation_act": "CONVERSATION_CONTINUATION"},
    )
    text = " ".join(turn["content"] for turn in history)

    assert "الفرع الثاني" in text
    assert "آخر نقطة في الفرع الثاني" in text
    assert "الفرع الأول" not in text

def test_named_independent_dialogue_topic_clears_unrelated_current_file():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    orchestrator.context.current_file = "old_project/main.py"

    manager._clear_unrelated_execution_file(
        ContextTransition.NEW_INDEPENDENT,
        {
            "intent": Intent.PERSONAL_CHAT,
            "target": "الرسم والنحت",
        },
    )
    assert orchestrator.context.current_file is None

    orchestrator.context.current_file = "main.py"
    manager._clear_unrelated_execution_file(
        ContextTransition.NEW_INDEPENDENT,
        {
            "intent": Intent.MODIFY_FILE,
            "target": "main.py",
        },
    )
    assert orchestrator.context.current_file == "main.py"


def test_subjectless_independent_social_topic_clears_stale_technical_subject(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.last_topic = "CSRF"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"

    result = manager.process("اريد اقتراحات اخرى في مجال اخر")

    assert result["status"] == "success"
    assert result["source"] == "local_social"
    assert memory.state.last_topic is None
    assert memory.state.last_entity_type is None
    assert memory.state.last_intent == "personal_chat"
    assert memory.state.exchange_archive[-1]["context_transition"] == "new_independent"
    assert calls == []
    assert orchestrator.calls == []

def test_failed_independent_social_reply_still_clears_stale_technical_subject():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    memory = DialogueMemory(ContextStore())
    memory.state.last_topic = "CSRF"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"
    memory.state.exchange_archive = [{
        "session_id": memory.state.session_id,
        "user": "اشرح CSRF",
        "assistant": "شرح سابق",
        "target": "CSRF",
        "intent": "cyber_explain",
        "context_kind": "dialogue",
        "conversation_domain": "technical",
    }]

    memory.update(
        "اريد اقتراحات اخرى في مجال اخر",
        {
            "status": "error",
            "error": "provider unavailable",
            "text": "تعذر الاتصال بالمزود",
            "semantic_request": {"context_kind": "social"},
        },
        mode="CHAT",
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "target": "",
            "entity_type": "REFERENCE",
            "conversation_domain": "social",
            "conversation_act": "CASUAL_CONVERSATION",
        },
        context_transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert memory.state.last_topic is None
    assert memory.state.last_entity_type is None
    assert memory.state.last_intent == "personal_chat"
    assert len(memory.state.exchange_archive) == 1
    assert all(item.get("assistant") != "تعذر الاتصال بالمزود"
               for item in memory.state.exchange_archive)


def test_dialogue_history_recall_is_read_only_for_active_topic_and_archive():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    memory = DialogueMemory(ContextStore())
    sid = memory.state.session_id
    memory.state.last_topic = "SQL Injection"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"
    memory.state.exchange_archive = [{
        "session_id": sid,
        "user": "اشرح SQL Injection",
        "assistant": "توقفنا عند آلية الحدوث",
        "target": "SQL Injection",
        "intent": "cyber_explain",
        "context_kind": "dialogue",
        "conversation_domain": "technical",
        "context_transition": "new_independent",
    }]
    before = memory.snapshot()

    memory.update(
        "ما الموضوع الذي كنا نشرحه في رسالتي السابقة؟",
        {
            "status": "success",
            "text": "بحسب سجل الحوار المحفوظ: SQL Injection",
            "source": "dialogue_memory",
            "semantic_request": {"context_kind": "dialogue"},
        },
        mode="CHAT",
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "target": "",
            "entity_type": "REFERENCE",
            "conversation_domain": "general",
            "conversation_act": "CONVERSATION_HISTORY_QUERY",
        },
        context_transition=ContextTransition.REFERENCE,
    )

    after = memory.snapshot()
    assert after["last_topic"] == before["last_topic"] == "SQL Injection"
    assert after["last_intent"] == before["last_intent"] == "cyber_explain"
    assert after["exchange_archive"] == before["exchange_archive"]
    assert after["history"] == before["history"]


def test_system_session_restore_does_not_overwrite_dialogue_owned_state():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    memory = DialogueMemory(ContextStore())
    memory.state.last_topic = "SQL Injection"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"
    memory.state.exchange_archive = [{
        "session_id": memory.state.session_id,
        "user": "اشرح SQL Injection",
        "assistant": "توقفنا عند آلية الحدوث",
        "target": "SQL Injection",
        "intent": "cyber_explain",
        "context_kind": "dialogue",
        "conversation_domain": "technical",
    }]
    before = memory.snapshot()

    memory.update(
        "استرجع الجلسة السابقة",
        {
            "status": "success",
            "text": "ملخص جلسة العمل",
            "semantic_request": {"context_kind": "system"},
        },
        mode="SYSTEM",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "entity_type": "REFERENCE",
            "conversation_domain": "system",
            "conversation_act": "ASSISTANT_STATE_QUERY",
        },
        context_transition=ContextTransition.NEW_INDEPENDENT,
    )

    after = memory.snapshot()
    assert after["last_topic"] == "SQL Injection"
    assert after["last_intent"] == "cyber_explain"
    assert after["exchange_archive"] == before["exchange_archive"]
    assert after["history"] == before["history"]


def test_interrupted_dialogue_recovery_phrase_is_classified_before_work_resume():
    result = classify_conversation_semantics(
        "استرجع النقاش الذي انقطع عندما انتقلنا إلى موضوع آخر، ثم واصل من آخر نقطة توقفنا عندها، دون أن أذكر اسم الموضوع أو ألخص ما قيل."
    )

    assert result["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert result["response_attributes"]["dialogue_recovery"] == "interrupted_branch"
    assert result["conversation_domain"] == "general"


def test_interrupted_dialogue_recovery_selects_previous_archived_branch_not_current():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    sid = memory.state.session_id
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "ناقشنا الشفافية في خوارزميات التوصية",
            "assistant": "توقفنا عند قياس أثر تغيير العوامل تدريجيًا",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "انتقلنا إلى موضوع الرسم",
            "assistant": "بدأنا مناقشة الرسم",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "explicit_switch",
        },
        {
            "session_id": sid,
            "user": "تفاصيل تنفيذ سرية",
            "assistant": "نتائج عمل سرية",
            "context_kind": "work",
            "conversation_domain": "work",
            "context_transition": "continue",
        },
    ]
    parsed = {
        "conversation_act": "CONVERSATION_CONTINUATION",
        "response_attributes": {"dialogue_recovery": "interrupted_branch"},
    }

    history = manager._history_for_transition(ContextTransition.AMBIGUOUS, parsed)
    rendered = " ".join(turn["content"] for turn in history)

    assert "الشفافية في خوارزميات التوصية" in rendered
    assert "قياس أثر تغيير العوامل تدريجيًا" in rendered
    assert "بدأنا مناقشة الرسم" not in rendered
    assert "نتائج عمل سرية" not in rendered

def test_interrupted_dialogue_recovery_routes_previous_branch_to_chat_prompt(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.last_topic = "موضوع الرسم"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "personal_chat"
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "ناقشنا الشفافية في خوارزميات التوصية",
            "assistant": "توقفنا عند قياس أثر تغيير العوامل تدريجيًا",
            "target": None,
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "انتقلنا إلى موضوع الرسم",
            "assistant": "بدأنا مناقشة الرسم",
            "target": "موضوع الرسم",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "explicit_switch",
        },
    ]

    result = manager.process(
        "استرجع النقاش الذي انقطع عندما انتقلنا إلى موضوع آخر، ثم واصل من آخر نقطة توقفنا عندها، دون أن أذكر اسم الموضوع أو ألخص ما قيل."
    )

    assert result["status"] == "success"
    assert len(calls) == 1
    assert "الشفافية في خوارزميات التوصية" in calls[0][0]
    assert "قياس أثر تغيير العوامل تدريجيًا" in calls[0][0]
    assert "بدأنا مناقشة الرسم" not in calls[0][0]
    assert orchestrator.calls == []




def test_short_resume_and_stopping_point_phrases_are_classified_as_dialogue():
    for text in ("اكمل", "تابع", "واصل"):
        signal = classify_conversation_semantics(text)
        assert signal["conversation_act"] == "CONVERSATION_CONTINUATION"

    for text in (
        "أكمل من نفس النقطة التي توقفنا فيها",
        "نعم نكمل من نفس النقطة التي توقفنا فيها",
    ):
        signal = classify_conversation_semantics(text)
        assert signal["conversation_act"] == "CONVERSATION_CONTINUATION"

    for text in ("أين توقفنا", "اين وصلنا", "وين وقفنا"):
        signal = classify_conversation_semantics(text)
        assert signal["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
        assert signal["response_attributes"]["dialogue_response_mode"] == "summary"

    # A bare confirmation is not itself a continuation instruction.
    assert classify_conversation_semantics("نعم")["conversation_act"] != "CONVERSATION_CONTINUATION"


def test_unnamed_topic_return_routes_selected_prior_branch_instead_of_dumping_archive(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.last_topic = "CSRF"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"
    memory.state.context_history = [{
        "entity": "SQL Injection",
        "entity_type": "CONCEPT",
        "action": "cyber_explain",
    }]
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "اشرح SQL Injection",
            "assistant": "توقفنا في SQL Injection عند آلية الحدوث.",
            "target": "SQL Injection",
            "intent": "cyber_explain",
            "conversation_domain": "technical",
            "context_kind": "dialogue",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "اشرح CSRF",
            "assistant": "بدأنا شرح CSRF من البداية.",
            "target": "CSRF",
            "intent": "cyber_explain",
            "conversation_domain": "technical",
            "context_kind": "dialogue",
            "context_transition": "explicit_switch",
        },
    ]

    result = manager.process(
        "استرجع النقاش الذي انقطع عندما انتقلنا إلى موضوع آخر، ثم واصل من آخر نقطة توقفنا عندها، دون أن أذكر اسم الموضوع أو ألخص ما قيل."
    )

    assert result["status"] == "success"
    assert result.get("source") != "dialogue_memory"
    assert memory.state.last_topic == "SQL Injection"
    assert memory.state.last_entity_type == "CONCEPT"
    assert memory.state.last_intent == "cyber_explain"
    assert memory.active_context_entity()["entity"] == "SQL Injection"
    assert memory.active_context_entity()["action"] == "cyber_explain"
    assert calls
    prompt = calls[-1][0]
    assert "SQL Injection" in prompt
    assert "توقفنا في SQL Injection عند آلية الحدوث" in prompt
    assert "بدأنا شرح CSRF من البداية" not in prompt

    continued = manager.process("اكمل")
    assert continued["status"] == "success"
    assert "SQL Injection" in calls[-1][0]
    assert "بدأنا شرح CSRF من البداية" not in calls[-1][0]


def test_explicit_friendly_chat_in_arabic_does_not_inherit_technical_branch(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.last_topic = "CSRF"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"

    result = manager.process("نريد أن نتحدث فقط محادثة ودية")

    assert result["status"] == "success"
    assert result["source"] == "local_social"
    assert "بعيدًا عن العمل والمهام" in result["text"]
    assert "CSRF" not in result["text"]
    assert orchestrator.calls == []

def test_dialogue_recall_feature_discussion_is_not_routed_as_history_recall(monkeypatch):
    phrases = (
        "حاليا نحن نطور سياق الحوار",
        "نعم تحسين طبقات الذاكرة واسترجاع الحوار بشكل صحيح وسليم",
        "نريد تصحيح مسار الحوار واسترجاعه داخل الوكيل",
    )
    for phrase in phrases:
        manager, memory, orchestrator, calls = _manager(monkeypatch)

        assert not manager._dialogue_recall_requested(phrase, {})
        result = manager.process(phrase)

        assert result.get("status") != "needs_clarification", phrase
        assert "لا أجد موضوعًا حواريًا واضحًا لاستعادته" not in result.get("text", ""), phrase
        assert orchestrator.calls or calls, phrase




def test_contextual_yes_i_know_continues_dialogue_only_after_assistant_question(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.exchange_archive = [{
        "session_id": sid,
        "user": "نحن نطور استمرارية الحوار",
        "assistant": "وصلنا إلى فحص اختيار الفرع السابق بدل بدء موضوع جديد.",
        "target": None,
        "intent": "personal_chat",
        "conversation_domain": "general",
        "context_kind": "dialogue",
        "context_transition": "continue",
    }]
    memory.state.add_turn(
        role="assistant",
        content="هل تريد أن نتابع فحص اختيار الفرع السابق؟",
        context_kind="dialogue",
        conversation_domain="general",
        session_id=sid,
    )

    result = manager.process("نعم اعرف")

    assert result["status"] == "success"
    assert result["source"] == "llm"
    assert result["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert "وصلنا إلى فحص اختيار الفرع السابق" in calls[-1][0]
    assert "لا تبدأ شرحًا عامًا جديدًا" in calls[-1][1]["system"]
    assert orchestrator.calls == []


def test_bare_discussion_continuation_uses_selected_branch_and_continuation_prompt(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "نحن نطور استمرارية الحوار",
            "assistant": "آخر نقطة كانت منع استرجاع الحوار من سرقة مسار مناقشة التطوير.",
            "target": None,
            "intent": "personal_chat",
            "conversation_domain": "general",
            "context_kind": "dialogue",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "استكمل العمل في الملف secret.py",
            "assistant": "تفاصيل عمل لا تدخل في الحوار العام.",
            "target": "secret.py",
            "intent": "modify_file",
            "conversation_domain": "work",
            "context_kind": "work",
            "context_transition": "continue",
        },
    ]

    result = manager.process("اكمل النقاش")

    assert result["status"] == "success"
    assert result["source"] == "llm"
    assert result["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert "آخر نقطة كانت منع استرجاع الحوار" in calls[-1][0]
    assert "secret.py" not in calls[-1][0]
    assert "لا تبدأ شرحًا عامًا جديدًا" in calls[-1][1]["system"]
    assert orchestrator.calls == []



def test_art_topic_declaration_replaces_stale_technical_branch_before_continuation(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    memory.state.last_topic = "CSRF"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "cyber_explain"

    opened = manager.process("موضوع الرسم والنحت")

    assert opened["status"] == "success"
    assert memory.state.last_topic == "الرسم والنحت"
    assert memory.state.last_intent == "personal_chat"

    continued = manager.process("اكمل الشرح")

    assert continued["status"] == "success"
    assert continued["semantic_request"]["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert "الرسم والنحت" in calls[-1][0]
    assert "CSRF" not in calls[-1][0]
    assert orchestrator.calls == []


def test_dialogue_history_recall_excludes_system_and_execution_exchanges(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.exchange_archive = [
        {
            "session_id": sid,
            "user": "ناقشنا موضوعًا اجتماعيًا",
            "assistant": "رد حواري مسموح",
            "context_kind": "dialogue",
            "conversation_domain": "general",
            "context_transition": "new_independent",
        },
        {
            "session_id": sid,
            "user": "بيانات جلسة نظام سرية",
            "assistant": "تفاصيل نظام لا تخص الحوار",
            "context_kind": "system",
            "conversation_domain": "system",
            "context_transition": "continue",
        },
        {
            "session_id": sid,
            "user": "أمر تنفيذ خاص",
            "assistant": "مخرجات تنفيذ خاصة",
            "context_kind": "execution",
            "conversation_domain": "execution",
            "context_transition": "continue",
        },
        {
            "session_id": sid,
            "user": "تفاصيل عمل خاصة",
            "assistant": "مخرجات عمل خاصة",
            "context_kind": "work",
            "conversation_domain": "work",
            "context_transition": "continue",
        },
    ]

    result = manager._answer_dialogue_history(
        "اكتب ملخص حوار الجلسة",
        "summary",
        memory.state.exchange_archive,
    )

    assert result["status"] == "success"
    assert "موضوعًا اجتماعيًا" in result["text"]
    assert "رد حواري مسموح" in result["text"]
    for private_marker in (
        "جلسة نظام سرية",
        "تفاصيل نظام لا تخص الحوار",
        "أمر تنفيذ خاص",
        "مخرجات تنفيذ خاصة",
        "تفاصيل عمل خاصة",
        "مخرجات عمل خاصة",
    ):
        assert private_marker not in result["text"]
    assert calls == []
    assert orchestrator.calls == []


def test_previous_session_phrase_recalls_dialogue_instead_of_work_checkpoint(monkeypatch):
    manager, memory, orchestrator, calls = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.last_topic = "الشفافية في خوارزميات التوصية"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.last_intent = "personal_chat"
    memory.state.exchange_archive = [{
        "session_id": sid,
        "user": "ناقشنا الشفافية في خوارزميات التوصية",
        "assistant": "توقفنا عند قياس أثر تغيير العوامل تدريجيًا",
        "target": "الشفافية في خوارزميات التوصية",
        "intent": "personal_chat",
        "context_kind": "dialogue",
        "conversation_domain": "general",
        "context_transition": "new_independent",
    }]

    result = manager.process("استرجع الجلسة السابقة")

    assert result["source"] == "dialogue_memory"
    assert "الشفافية في خوارزميات التوصية" in result["text"]
    assert "قياس أثر تغيير العوامل تدريجيًا" in result["text"]
    assert orchestrator.calls == []
    assert calls == []
    assert memory.state.last_topic == "الشفافية في خوارزميات التوصية"
    assert memory.state.last_intent == "personal_chat"


def test_previous_dialogue_and_topic_memory_phrases_are_not_work_session_routes():
    for phrase in (
        "الجلسة السابقة",
        "الجلسه السابقه",
        "حوارنا السابق",
        "موضوعنا السابق",
        "عن موضوعنا السابق",
        "استرجع الجلسة السابقة",
        "استرجاع الجلسة السابقة",
    ):
        result = classify_conversation_semantics(phrase)
        assert result["conversation_act"] == "CONVERSATION_HISTORY_QUERY", phrase
        assert result["response_attributes"]["dialogue_response_mode"] == "summary", phrase

    recalled = classify_conversation_semantics(
        "هل تتذكر موضوع الرسم والنحت والنقش البارز"
    )
    assert recalled["conversation_act"] == "CONVERSATION_HISTORY_QUERY"
    assert recalled["response_attributes"]["dialogue_response_mode"] == "summary"


def test_continue_explanation_is_classified_as_dialogue_continuation():
    result = classify_conversation_semantics("اكمل الشرح")
    assert result["conversation_act"] == "CONVERSATION_CONTINUATION"
    assert result["conversation_domain"] == "general"
