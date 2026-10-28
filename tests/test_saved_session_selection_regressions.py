from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.memory.session_state import session_selector


def test_session_selector_keeps_explicit_number_and_saved_session_list():
    assert session_selector("استرجع الجلسة 3") == {
        "kind": "number", "number": 3, "report_mode": "standard"
    }
    assert session_selector("استرجع سياق حوار الجلسة المحفوظة")["kind"] == "list"


def test_session_selector_extracts_numbers_after_saved_session_descriptors():
    cases = (
        ("اكتب ملخص الجلسة المحفوظة رقم 30", 30, "full"),
        ("اعرض ملخص الجلسة المحفوظة رقم 1", 1, "full"),
        ("اكتب تقرير الجلسة المحفوظة رقم 22", 22, "full"),
        ("استرجع جلسة العمل المحفوظة رقم 3", 3, "standard"),
    )
    for request, number, report_mode in cases:
        selected = session_selector(request)
        assert selected["kind"] == "number", (request, selected)
        assert selected["number"] == number, (request, selected)
        assert selected["report_mode"] == report_mode, (request, selected)


def test_orchestrator_restores_the_selected_number_not_the_latest(monkeypatch):
    sessions = [
        {"session_id": "session-1", "session_type": "dialogue", "status": "completed",
         "active_goal": "الفن", "dialogue_state": {"session_id": "dialogue-1"}},
        {"session_id": "session-2", "session_type": "dialogue", "status": "completed",
         "active_goal": "Python", "dialogue_state": {"session_id": "dialogue-2"}},
        {"session_id": "session-3", "session_type": "work", "status": "paused",
         "active_goal": "عمل آخر", "next_step": "متابعة"},
    ]
    selected = []
    agent = SimpleNamespace(
        restore_session_snapshot=lambda data: selected.append(data) or True,
        restore_session_context=lambda: False,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    orchestrator = Orchestrator(agent)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_index", lambda: sessions)
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_id",
        lambda session_id: next((item for item in sessions if item["session_id"] == session_id), {}),
    )
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: sessions[-1])
    monkeypatch.setattr("lab_v4_dev.memory.session_state.recoverable_work_checkpoint", lambda data: None)

    result = orchestrator.handle(
        "استرجع الجلسة 1",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "system",
            "session_selector": {"kind": "number", "number": 1, "report_mode": "standard"},
        },
    )

    assert result["status"] == "success"
    assert selected and selected[0]["session_id"] == "session-1"
    assert "الفن" in result["text"]


def test_dialogue_topic_survives_example_and_ordinal_return(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda prompt, **kwargs: calls.append(prompt) or {
            "status": "success", "text": "رد حواري", "provider_used": "test"
        },
    )
    manager = ConversationManager(
        SimpleNamespace(context=ContextStore()),
        DialogueMemory(ContextStore()),
    )
    manager.process("عن موضوع الفن")
    manager.process("الرسم والنحت والنقش البارز")
    manager.process("مثلا اعطيني مثال")
    result = manager.process("عن الموضوع الذي كنا نتحدث فيه قبل ردين")

    assert result["status"] == "success"
    assert result.get("source") != "dialogue_memory"
    assert calls
    assert "الرسم والنحت والنقش البارز" in calls[-1]


def test_saved_dialogue_is_not_loaded_implicitly_by_a_new_dialogue_memory():
    memory = DialogueMemory(ContextStore())
    assert memory.state.last_topic is None
    assert memory.state.exchange_archive == []


def test_named_social_switch_and_correction_stay_in_dialogue_route(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda prompt, **kwargs: {"status": "success", "text": "رد حواري", "provider_used": "test"},
    )
    orchestrator = SimpleNamespace(
        context=ContextStore(),
        handle=lambda *args, **kwargs: calls.append(kwargs.get("parsed")) or {
            "status": "success", "text": "ORCHESTRATOR"
        },
    )
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)

    manager.process("دعنا نتحدث عن الكتب")
    switched = manager.process("حسنا دعنا ننتقل لكتب علم النفس")
    corrected = manager.process("لا قلت موضوع الكتب الذي كنا نناقشه")
    continued = manager.process("اجل اكمل")

    assert getattr(switched["intent"], "value", switched["intent"]) == "personal_chat"
    assert corrected["source"] != "dialogue_memory"
    assert continued["source"] != "dialogue_memory"
    assert not calls
    assert memory.state.last_topic == "الكتب"

def test_previous_saved_dialogue_selector_is_distinct_from_latest_work_session():
    selected = session_selector("حسنا ماذا كنا نقول في الجلسة السابقة")
    assert selected == {"kind": "previous_dialogue", "report_mode": "standard"}
    saved_dialogue = session_selector("هل تستطيع استرجاع حوار الجلسة السابقة المحفوظة")
    assert saved_dialogue == {"kind": "previous_dialogue", "report_mode": "standard"}
    # Generic continuity remains owned by the current dialogue layer.
    assert session_selector("استرجع الجلسة السابقة")["kind"] == "latest"


def test_previous_dialogue_report_skips_live_dialogue_and_work_checkpoint(monkeypatch):
    from lab_v4_dev.memory.session_state import session_selector

    sessions = [
        {
            "session_id": "prior-dialogue-record",
            "session_type": "dialogue",
            "status": "completed",
            "active_goal": "النحت البارز",
            "dialogue_state": {
                "session_id": "prior-dialogue-state",
                "last_topic": "النحت البارز",
                "history": [{"role": "user", "content": "كنا نتحدث عن النحت البارز"}],
                "exchange_archive": [],
            },
        },
        {
            "session_id": "live-dialogue-record",
            "session_type": "dialogue",
            "status": "active",
            "active_goal": "التحية",
            "dialogue_state": {
                "session_id": "live-dialogue-state",
                "last_topic": "التحية",
                "history": [],
                "exchange_archive": [],
            },
        },
        {
            "session_id": "latest-work-record",
            "session_type": "work",
            "status": "paused",
            "active_goal": "إصلاح الكود",
            "context_state": {"current_file": "agent.py"},
        },
    ]
    restored = []
    agent = SimpleNamespace(
        dialogue_memory=SimpleNamespace(
            state=SimpleNamespace(session_id="live-dialogue-state")
        ),
        restore_session_snapshot=lambda data: restored.append(data) or True,
        restore_session_context=lambda: False,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    orchestrator = Orchestrator(agent)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_index", lambda: sessions)
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_id",
        lambda session_id: next(
            (item for item in sessions if item["session_id"] == session_id), {}
        ),
    )
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: sessions[-1])
    monkeypatch.setattr("lab_v4_dev.memory.session_state.recoverable_work_checkpoint", lambda data: None)

    result = orchestrator.handle(
        "حسنا ماذا كنا نقول في الجلسة السابقة",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "general",
            "session_selector": session_selector("حسنا ماذا كنا نقول في الجلسة السابقة"),
        },
    )

    assert result["status"] == "success"
    assert result["source"] == "saved_session_report"
    assert result["context_action"] == "read_only_report"
    assert result["context_restored"] is None
    assert not restored, "a content-summary request must not mutate active dialogue/work context"
    assert "النحت البارز" in result["text"]
    assert "agent.py" not in result["text"]

def test_session_selector_recognizes_all_saved_session_summary_requests():
    for request in (
        "اعرض ملخصات كل الجلسات",
        "أعطني ملخصات جميع الجلسات المحفوظة",
        "لخص كل الجلسات",
        "اعرض كل الجلسات وملخصاتها",
        "اكتب ملخصات الجلسات المحفوظة كلها",
        "اعرض نلخصات الجلسات السابقة كلها",
        "اعرض ملخصات الجلسة المحفوظة",
    ):
        selected = session_selector(request)
        assert selected["kind"] == "list", (request, selected)
        assert selected["report_mode"] == "summaries", (request, selected)


def test_explicit_previous_session_request_is_not_downgraded_to_live_history():
    # Joined words are common in mobile terminal input and must still select
    # persisted-session restoration instead of the live dialogue archive.
    assert session_selector("ماذاكنا نقول في اخر جلسة")["kind"] == "previous_dialogue"
    for request in (
        "ماذا كنا نقول في اخر جلسة",
        "تحقق اولا ثم اكتب ملخص ماذا كنا نقول في الجلسة السابقة",
        "اعرض سياق الجلسة السابقة",
        "عن اي موضوع كنا نتحدث في الجلسة المحفوظة اكتب تقرير",
    ):
        selected = session_selector(request)
        assert selected["kind"] in {"previous_dialogue", "latest", "list"}, (request, selected)


def test_session_selector_routes_saved_session_summary_wording_to_summary_report():
    for request in (
        "اعرض ملخصات الجلسة المحفوظة",
        "اكتب ملخص الجلسة المحفوظة",
        "قلت لك اكتب ملخصات الجلسات المحفوظة كلها",
    ):
        selected = session_selector(request)
        assert selected["kind"] in {"list", "latest"}, (request, selected)
        assert selected["report_mode"] in {"summaries", "full"}, (request, selected)


def test_explicit_previous_session_request_reaches_orchestrator(monkeypatch):
    calls = []
    orchestrator = SimpleNamespace(
        context=ContextStore(),
        handle=lambda text, parsed=None, **kwargs: (
            calls.append((text, parsed, kwargs))
            or {"status": "success", "text": "SAVED SESSION PATH"}
        ),
    )
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("ماذا كنا نقول في اخر جلسة")

    assert result["status"] == "success"
    assert calls, "explicit saved-session request must reach the orchestrator"
    parsed = calls[-1][1]
    assert parsed["intent"] == Intent.SESSION_RESTORE
    assert parsed["session_selector"]["kind"] == "previous_dialogue"
    assert result["text"] == "SAVED SESSION PATH"


def test_all_saved_session_summaries_request_reaches_orchestrator(monkeypatch):
    calls = []
    orchestrator = SimpleNamespace(
        context=ContextStore(),
        handle=lambda text, parsed=None, **kwargs: (
            calls.append((text, parsed, kwargs))
            or {"status": "success", "text": "ALL SAVED SESSION SUMMARIES"}
        ),
    )
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("قلت لك اكتب ملخصات الجلسات المحفوظة كلها")

    assert result["status"] == "success"
    assert calls, "all-session summary request must reach the orchestrator"
    parsed = calls[-1][1]
    assert parsed["intent"] == Intent.SESSION_RESTORE
    assert parsed["session_selector"]["kind"] == "list"
    assert parsed["session_selector"]["report_mode"] == "summaries"
    assert result["text"] == "ALL SAVED SESSION SUMMARIES"


def test_orchestrator_returns_semantic_summary_for_each_saved_session(monkeypatch):
    sessions = [
        {
            "session_id": "dialogue-art-001",
            "session_type": "dialogue",
            "status": "completed",
            "active_goal": "الرسم والنحت",
            "next_step": "متابعة النقش البارز",
            "dialogue_state": {
                "session_id": "dialogue-art-001",
                "last_topic": "الرسم والنحت",
                "history": [],
                "exchange_archive": [],
            },
        },
        {
            "session_id": "work-tests-002",
            "session_type": "work",
            "status": "paused",
            "active_goal": "إصلاح الاختبارات",
            "next_step": "تشغيل الاختبارات المستهدفة",
            "completed_work": ["إضافة اختبار ارتدادي"],
            "context_state": {"subject": "إصلاح الاختبارات"},
        },
    ]
    agent = SimpleNamespace(
        restore_session_snapshot=lambda _data: True,
        restore_session_context=lambda: False,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    orchestrator = Orchestrator(agent)
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_index",
        lambda: sessions,
    )
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_id",
        lambda session_id: next(
            (item for item in sessions if item["session_id"] == session_id), {}
        ),
    )

    request = "اعرض ملخصات كل الجلسات"
    result = orchestrator.handle(
        request,
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "system",
            "session_selector": session_selector(request),
        },
    )

    assert result["status"] == "success"
    assert "ملخصات الجلسات المحفوظة" in result["text"]
    assert "الرسم والنحت" in result["text"]
    assert "متابعة النقش البارز" in result["text"]
    assert "إصلاح الاختبارات" in result["text"]
    assert "تشغيل الاختبارات المستهدفة" in result["text"]
    assert len(result["sessions"]) == 2


def test_dialogue_restore_summary_uses_saved_topic_and_stop_point():
    from lab_v4_dev.memory.session_state import build_session_restore_summary

    sid = "dialogue-summary-test"
    saved = {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "last_topic": "النحت البارز",
            "exchange_archive": [
                {
                    "session_id": sid,
                    "user": "ما الفرق بين النحت البارز والغائر؟",
                    "assistant": "الفرق هو اتجاه بروز الشكل عن السطح.",
                    "target": "النحت البارز",
                }
            ],
        },
    }
    summary = build_session_restore_summary(saved)
    assert "ملخص الحوار المحفوظ" in summary
    assert "النحت البارز" in summary
    assert "نقطة التوقف" in summary
    assert "ما نوقش فعليًا في الحوار" in summary
    assert "قارن الحوار بين «النحت البارز والغائر»." in summary
    assert "ما الفرق بين النحت البارز والغائر؟" not in summary
    assert "الفرق هو اتجاه بروز الشكل عن السطح." not in summary


def test_explicit_saved_transcript_request_selects_transcript_mode():
    from lab_v4_dev.memory.session_state import build_session_restore_summary, session_selector

    sid = "dialogue-transcript-test"
    saved = {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "last_topic": "الرسم",
            "exchange_archive": [
                {"session_id": sid, "user": "رسالة أصلية 1", "assistant": "رد أصلي 1"},
                {"session_id": sid, "user": "رسالة أصلية 2", "assistant": "رد أصلي 2"},
            ],
        },
    }
    selected = session_selector("اعرض نص الحوار المحفوظ حرفيًا")
    transcript = build_session_restore_summary(saved, report_mode=selected["report_mode"])
    assert selected["kind"] == "previous_dialogue"
    assert selected["report_mode"] == "transcript"
    assert transcript.index("رسالة أصلية 1") < transcript.index("رد أصلي 1")
    assert transcript.index("رد أصلي 1") < transcript.index("رسالة أصلية 2")


def test_explicit_saved_transcript_request_is_not_downgraded_to_live_dialogue():
    calls = []
    orchestrator = SimpleNamespace(
        context=ContextStore(),
        handle=lambda text, parsed=None, **kwargs: (
            calls.append((text, parsed)) or {"status": "success", "text": "TRANSCRIPT PATH"}
        ),
    )
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))
    result = manager.process("اعرض نص الحوار المحفوظ حرفيًا")

    assert result["status"] == "success"
    assert calls
    parsed = calls[-1][1]
    assert parsed["intent"] == Intent.SESSION_RESTORE
    assert parsed["session_selector"]["kind"] == "previous_dialogue"
    assert parsed["session_selector"]["report_mode"] == "transcript"

def test_work_session_summary_request_selects_work_only_summaries():
    selected = session_selector("ما مضمون جلسات العمل؟")
    assert selected == {
        "kind": "list",
        "session_type": "work",
        "report_mode": "summaries",
    }


def test_unspecified_previously_discussed_topic_selects_saved_dialogue():
    selected = session_selector("ما الموضوع الذي ناقشناه سابقًا؟")
    assert selected["kind"] == "previous_dialogue"
    assert selected["report_mode"] == "standard"

def test_work_session_summary_lists_work_records_without_dialogues(monkeypatch):
    sessions = [
        {
            "session_id": "dialogue-art-filter",
            "session_type": "dialogue",
            "status": "completed",
            "active_goal": "الرسم والنحت",
            "dialogue_state": {
                "session_id": "dialogue-art-filter",
                "last_topic": "الرسم والنحت",
                "history": [],
                "exchange_archive": [],
            },
        },
        {
            "session_id": "work-project-filter",
            "session_type": "work",
            "status": "paused",
            "active_goal": "إصلاح الاختبارات",
            "next_step": "تشغيل الاختبارات المستهدفة",
            "context_state": {"subject": "إصلاح الاختبارات"},
        },
    ]
    agent = SimpleNamespace(
        restore_session_snapshot=lambda _data: True,
        restore_session_context=lambda: False,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    orchestrator = Orchestrator(agent)
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_index",
        lambda: sessions,
    )
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_id",
        lambda session_id: next(
            (item for item in sessions if item["session_id"] == session_id), {}
        ),
    )

    request = "ما مضمون جلسات العمل؟"
    result = orchestrator.handle(
        request,
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "system",
            "session_selector": session_selector(request),
        },
    )

    assert result["status"] == "success"
    assert "إصلاح الاختبارات" in result["text"]
    assert "تشغيل الاختبارات المستهدفة" in result["text"]
    assert "الرسم والنحت" not in result["text"]
    assert len(result["sessions"]) == 1

def test_prior_session_content_questions_select_saved_dialogue_semantically():
    for request in (
        "نعم اريد ان نتحدث عن موضوع في الجلسة السابقة",
        "ما مظمون الجلسة السابقة",
        "ماذا كنا نقول في اخر جلسة اكتب ملخص الجلسة السابقة",
        "ماهو اخر موضوع ناقشناه سابقا",
    ):
        selected = session_selector(request)
        assert selected["kind"] == "previous_dialogue", (request, selected)

    # A generic restore command remains deliberately ambiguous without a
    # content question; do not silently change its established meaning.
    assert session_selector("استرجع الجلسة السابقة")["kind"] == "latest"


def test_previous_topic_recall_cannot_be_downgraded_to_live_history(monkeypatch):
    calls = []
    orchestrator = SimpleNamespace(
        context=ContextStore(),
        handle=lambda text, parsed=None, **kwargs: (
            calls.append((text, parsed))
            or {"status": "success", "text": "SAVED DIALOGUE OWNER"}
        ),
    )
    memory = DialogueMemory(orchestrator.context)
    # A populated live archive used to trigger a second routing decision that
    # stole this already-classified saved-dialogue request.
    memory.state.exchange_archive = [
        {
            "session_id": memory.state.session_id,
            "user": "نتحدث الآن عن التحية",
            "assistant": "هذا تبادل من الحوار الحي",
            "target": "التحية",
            "context_kind": "dialogue",
        }
    ]
    manager = ConversationManager(orchestrator, memory)
    result = manager.process("ماهو اخر موضوع ناقشناه سابقا")

    assert result["status"] == "success"
    assert result["text"] == "SAVED DIALOGUE OWNER"
    assert calls, "previous saved-dialogue requests must reach the session restore owner"
    parsed = calls[-1][1]
    assert parsed["intent"] == Intent.SESSION_RESTORE
    assert parsed["session_selector"]["kind"] == "previous_dialogue"

def test_live_dialogue_recall_is_not_mistaken_for_a_saved_session():
    for request in (
        "ماذا كنا نقول؟",
        "ماذا كنا نقول في الردود السابقة؟",
        "اكتب ملخص الحوار السابق عن الموضوع",
    ):
        selected = session_selector(request)
        assert selected["kind"] == "none", (request, selected)

    # Explicit session identity still routes to persisted-dialogue restoration.
    assert session_selector("ما مظمون الجلسة السابقة")["kind"] == "previous_dialogue"
    assert session_selector(
        "نعم اريد ان نتحدث عن موضوع في الجلسة السابقة"
    )["kind"] == "previous_dialogue"

def test_numbered_saved_session_summary_is_read_only_and_reports_the_selected_record(monkeypatch):
    sessions = [
        {
            "session_id": "dialogue-art-record",
            "session_type": "dialogue",
            "active_goal": "الفن التجريدي",
            "dialogue_state": {
                "session_id": "dialogue-art-record",
                "last_topic": "الفن التجريدي",
                "exchange_archive": [
                    {
                        "session_id": "dialogue-art-record",
                        "user": "كيف نستخدم اللون في الفن التجريدي؟",
                        "assistant": "تختلف المعالجة بحسب التكوين والهدف التعبيري.",
                        "target": "الفن التجريدي وتقنيات اللون",
                    }
                ],
            },
        },
        {
            "session_id": "dialogue-python-record",
            "session_type": "dialogue",
            "active_goal": "Python",
            "dialogue_state": {
                "session_id": "dialogue-python-record",
                "last_topic": "Python",
                "exchange_archive": [
                    {
                        "session_id": "dialogue-python-record",
                        "user": "ما الفرق بين القائمة والقاموس؟",
                        "assistant": "القائمة تحفظ ترتيب العناصر، والقاموس يربط مفاتيح بقيم.",
                        "target": "هياكل البيانات في Python",
                    }
                ],
            },
        },
    ]
    restore_calls = []
    agent = SimpleNamespace(
        restore_session_snapshot=lambda data: restore_calls.append(data) or True,
        restore_session_context=lambda: restore_calls.append("current-context") or True,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    orchestrator = Orchestrator(agent)
    context_before = getattr(orchestrator.context, "last_result", None)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_index", lambda: sessions)
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_id",
        lambda session_id: next(
            (item for item in sessions if item["session_id"] == session_id), {}
        ),
    )
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: {})
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.recoverable_work_checkpoint",
        lambda data: None,
    )

    request = "اكتب ملخص الجلسة المحفوظة رقم 2"
    selected = session_selector(request)
    assert selected == {"kind": "number", "number": 2, "report_mode": "full"}

    result = orchestrator.handle(
        request,
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "system",
            "session_selector": selected,
        },
    )

    assert result["status"] == "success"
    assert result["source"] == "saved_session_report"
    assert result["context_action"] == "read_only_report"
    assert result["context_restored"] is None
    assert result["session_id"] == "dialogue-python-record"
    assert "Python" in result["text"]
    assert "هياكل البيانات في Python" in result["text"]
    assert "الفن التجريدي" not in result["text"]
    assert "ما الفرق بين القائمة والقاموس؟" not in result["text"]
    assert not restore_calls
    assert getattr(orchestrator.context, "last_result", None) is context_before

