from types import SimpleNamespace

from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.core.agent import Agent
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.core.contracts import RouteDecision, SessionRef
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.memory import session_state
from lab_v4_dev.memory.dialogue_knowledge import (
    analyze_dialogue_session,
    extract_exchange_knowledge,
    format_dialogue_analysis_report,
    retrieve_dialogue_evidence,
)


def _saved_session():
    sid = "knowledge-provenance-session"
    return {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid,
                    "exchange_id": "exchange-1",
                    "timestamp": "2026-11-01T10:00:00",
                    "target": "تنفيذ لوحة بالجبس",
                    "user": "استخدمت إطارًا خشبيًا وصببت الجبس بسماكة ثلاثة سنتيمترات.",
                    "assistant": "يمكنك ترك الجبس حتى يجف ثم تشكيل السطح.",
                },
                {
                    "session_id": sid,
                    "exchange_id": "exchange-2",
                    "timestamp": "2026-11-01T10:05:00",
                    "target": "تنفيذ لوحة بالجبس",
                    "user": "سأستخدم سكينًا ومفك براغٍ وملعقة لتشكيل الجبس.",
                    "assistant": "أقترح إضافة ورق صنفرة لتنعيم بعض الحواف.",
                },
                {
                    "session_id": sid,
                    "exchange_id": "exchange-3",
                    "timestamp": "2026-11-01T10:08:00",
                    "target": "تنفيذ لوحة بالجبس",
                    "user": "نعم، سأعتمد اقتراحك.",
                    "assistant": "يمكن استخدام الصنفرة بعد جفاف الجبس.",
                },
            ],
        },
    }


def test_knowledge_records_keep_speaker_and_source_exchange():
    analysis = analyze_dialogue_session(_saved_session())

    assert analysis["exchange_count"] == 3
    assert any(
        item["speaker"] == "user"
        and "إطارًا خشبيًا" in item["content"]
        and item["source_exchange_id"] == "exchange-1"
        for item in analysis["user_information"]
    )
    assert any(
        item["speaker"] == "assistant"
        and item["knowledge_type"] == "assistant_suggestion"
        and "ورق صنفرة" in item["content"]
        and item["source_exchange_id"] == "exchange-2"
        for item in analysis["assistant_information"]
    )
    assert any(item["relation"] == "accepts" for item in analysis["relationships"])


def test_new_detail_question_retrieves_original_exchange_with_provenance():
    evidence = retrieve_dialogue_evidence(_saved_session(), "ما الأدوات التي استخدمتها؟")

    assert evidence
    assert any("سكينًا" in item["user"] for item in evidence)
    assert any(item["exchange_id"] == "exchange-2" for item in evidence)


def test_full_analysis_report_separates_user_and_assistant_contributions():
    report = format_dialogue_analysis_report(_saved_session())

    assert "معلومات المستخدم المستخرجة" in report
    assert "مساهمات الوكيل واقتراحاته" in report
    assert "إطارًا خشبيًا" in report
    assert "ورق صنفرة" in report
    assert "التسلسل الزمني" in report


def test_dialogue_memory_persists_exchange_identity_and_derived_knowledge():
    memory = DialogueMemory(SimpleNamespace())
    memory.update(
        "أفضّل استخدام أدوات منزلية بسيطة.",
        {"status": "success", "text": "يمكنك البدء بالأدوات المتاحة لديك."},
        parsed={
            "intent": "personal_chat",
            "conversation_domain": "general",
            "conversation_act": "CASUAL_CONVERSATION",
            "target": "الأدوات المنزلية",
        },
        context_transition="new_independent",
    )

    exchange = memory.state.exchange_archive[-1]
    assert exchange["exchange_id"]
    assert exchange["timestamp"]
    assert exchange["knowledge_version"] == 2
    assert exchange["knowledge"]
    assert all(item["source_exchange_id"] == exchange["exchange_id"] for item in exchange["knowledge"])


def test_missing_detail_file_is_marked_as_compact_index_only(monkeypatch):
    monkeypatch.setattr(session_state, "load_session", lambda: {})
    monkeypatch.setattr(session_state, "_load_session_detail", lambda _sid: {})
    monkeypatch.setattr(
        session_state,
        "get_session_index",
        lambda: [{"session_id": "index-only-session", "session_type": "dialogue"}],
    )

    record = session_state.get_session_by_id("index-only-session")

    assert record["session_id"] == "index-only-session"
    assert record["_record_source"] == "index"
    assert record["_detail_available"] is False



def test_saved_question_provider_synthesis_requires_route_permission(monkeypatch):
    sid = "provider-evidence-session"
    session = {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid,
                    "exchange_id": "evidence-1",
                    "user": "سأستخدم سكينًا ومفكًا وملعقة لتشكيل الجبس.",
                    "assistant": "هذه أدوات منزلية مناسبة للتشكيل.",
                },
            ],
        },
    }
    observed = []
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_index",
        lambda: [session],
    )
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_number",
        lambda number: session if number == 1 else {},
    )
    monkeypatch.setattr(
        "lab_v4_dev.memory.session_state.get_session_by_id",
        lambda session_id: session if session_id == sid else {},
    )
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: {})
    monkeypatch.setattr("lab_v4_dev.memory.session_state.recoverable_work_checkpoint", lambda _data: None)

    def fake_gateway(prompt, **kwargs):
        observed.append(prompt)
        return {
            "status": "success",
            "text": "ذكر المستخدم السكين والمفك والملعقة. [التبادل 1]",
        }

    monkeypatch.setattr("lab_v4_dev.llm.gateway.ask", fake_gateway)
    agent = SimpleNamespace(
        allow_provider_session_synthesis=True,
        restore_session_snapshot=lambda _data: True,
        restore_session_context=lambda: True,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    decision = RouteDecision(
        route="L-SESSION",
        session_scope="saved_number",
        session_ref=SessionRef(session_id=sid, number=1),
        output_kind="summary",
        evidence_scope="saved_session",
        provider_allowed=True,
        intent=Intent.SESSION_RESTORE,
    )
    request = "ما الأدوات التي استخدمتها في الجلسة 1؟"
    result = Orchestrator(agent).handle(
        request,
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "session_selector": {
                "kind": "number",
                "number": 1,
                "report_mode": "recall",
                "output_kind": "summary",
            },
        },
        route_decision=decision,
    )

    assert result["status"] == "success"
    assert result["provider_synthesis_allowed"] is True, result
    assert result["provider_synthesis_attempted"] is True, result
    assert observed, result
    assert result["provider_synthesis_rejection_reason"] is None, result
    assert result["source"] == "saved_session_evidence_synthesis"
    assert result["provider_synthesis_used"] is True
    assert observed and "سأستخدم سكينًا" in observed[0]
    assert "evidence-1" in result["evidence_exchange_ids"]


def test_saved_question_provider_is_not_called_without_route_permission(monkeypatch):
    sid = "local-only-evidence-session"
    session = {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid,
                    "exchange_id": "local-evidence-1",
                    "user": "صببت الجبس بسماكة ثلاثة سنتيمترات.",
                    "assistant": "يمكن تشكيله بعد الجفاف.",
                },
            ],
        },
    }
    calls = []
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_index", lambda: [session])
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_by_number", lambda _n: session)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_by_id", lambda _sid: session)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: {})
    monkeypatch.setattr("lab_v4_dev.memory.session_state.recoverable_work_checkpoint", lambda _data: None)
    monkeypatch.setattr("lab_v4_dev.llm.gateway.ask", lambda *a, **k: calls.append(a) or {
        "status": "success", "text": "إجابة لا ينبغي استخدامها. [التبادل 1]"
    })
    agent = SimpleNamespace(
        allow_provider_session_synthesis=True,
        restore_session_snapshot=lambda _data: True,
        restore_session_context=lambda: True,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    decision = RouteDecision(
        route="L-SESSION",
        session_scope="saved_number",
        session_ref=SessionRef(session_id=sid, number=1),
        output_kind="summary",
        evidence_scope="saved_session",
        provider_allowed=False,
        intent=Intent.SESSION_RESTORE,
    )
    result = Orchestrator(agent).handle(
        "ما سماكة الجبس في الجلسة 1؟",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "session_selector": {
                "kind": "number", "number": 1, "report_mode": "recall", "output_kind": "summary"
            },
        },
        route_decision=decision,
    )

    assert result["status"] == "success"
    assert result["source"] == "saved_session_evidence_retrieval"
    assert result["provider_synthesis_used"] is False
    assert not calls


def test_orchestrator_refuses_to_analyze_compact_index_without_detail_file(monkeypatch):
    sid = "index-only-report-session"
    compact = {
        "session_id": sid,
        "session_type": "dialogue",
        "_record_source": "index",
        "_detail_available": False,
    }
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_index", lambda: [compact])
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_by_number", lambda _n: compact)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.get_session_by_id", lambda _sid: compact)
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: {})
    agent = SimpleNamespace(
        restore_session_snapshot=lambda _data: True,
        restore_session_context=lambda: True,
        runtime=None,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    decision = RouteDecision(
        route="L-SESSION",
        session_scope="saved_number",
        session_ref=SessionRef(session_id=sid, number=1),
        output_kind="report",
        evidence_scope="saved_session",
        provider_allowed=False,
        intent=Intent.SESSION_RESTORE,
    )
    result = Orchestrator(agent).handle(
        "اكتب تقريرًا تحليليًا عن الجلسة 1",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "session_selector": {
                "kind": "number", "number": 1, "report_mode": "full", "output_kind": "report"
            },
        },
        route_decision=decision,
    )

    assert result["status"] == "needs_clarification"
    assert result["source"] == "saved_session_detail_unavailable"



def test_cached_knowledge_is_rebuilt_when_original_exchange_changes():
    session = _saved_session()
    exchange = session["dialogue_state"]["exchange_archive"][0]
    exchange["knowledge_version"] = 2
    exchange["knowledge"] = extract_exchange_knowledge(
        exchange,
        session_id=session["session_id"],
        exchange_index=0,
    )
    assert any("إطارًا خشبيًا" in item["content"] for item in exchange["knowledge"])

    exchange["user"] = "استخدمت قالبًا معدنيًا وصببت الجبس بسماكة خمسة سنتيمترات."
    analysis = analyze_dialogue_session(session)

    assert any("قالبًا معدنيًا" in item["content"] for item in analysis["user_information"])
    assert not any("إطارًا خشبيًا" in item["content"] for item in analysis["user_information"])


def test_planned_actions_are_not_misreported_as_final_decisions():
    analysis = analyze_dialogue_session(_saved_session())

    assert any("سأستخدم سكينًا" in item["content"] for item in analysis["planned_actions"])
    assert not any("سأستخدم سكينًا" in item["content"] for item in analysis["decisions"])



def test_failed_dialogue_exchange_is_preserved_as_unresolved_raw_evidence():
    memory = DialogueMemory(SimpleNamespace())
    prompt = "ما التفاصيل التي ذكرتها عن طريقة تنفيذ العمل؟"
    memory.update(
        prompt,
        {"status": "error", "text": "تعذر إنتاج رد صالح."},
        parsed={
            "intent": "personal_chat",
            "conversation_domain": "general",
            "conversation_act": "CASUAL_CONVERSATION",
        },
        context_transition="continue",
    )
    session = {
        "session_id": memory.state.session_id,
        "dialogue_state": memory.snapshot(),
    }

    analysis = analyze_dialogue_session(session)

    assert analysis["exchange_count"] == 1
    assert memory.state.exchange_archive == []
    assert memory.state.failed_exchange_archive[-1]["user"] == prompt
    assert analysis["failed_exchanges"][0]["user_text"] == prompt
    assert any(item["content"] == prompt for item in analysis["unresolved_questions"])
    restored = DialogueMemory(SimpleNamespace())
    assert restored.restore_snapshot(memory.snapshot())
    assert restored.state.failed_exchange_archive[-1]["user"] == prompt
    assert retrieve_dialogue_evidence(session, "ما التفاصيل؟") == []


def test_agent_persists_changed_dialogue_state_even_when_response_fails():
    state = {"revision": 0}
    saves = []

    class Memory:
        def snapshot(self):
            return {"revision": state["revision"]}

    class Conversation:
        def process(self, _text):
            state["revision"] += 1
            return {"status": "error", "text": "provider unavailable"}

    fake_agent = SimpleNamespace(
        loop=object(),
        state=SimpleNamespace(mode="normal"),
        conv_manager=Conversation(),
        dialogue_memory=Memory(),
        _save_dialogue_checkpoint=lambda: saves.append("saved"),
    )

    result = Agent.run(fake_agent, "سؤال لم يحصل على إجابة.")

    assert result["status"] == "error"
    assert saves == ["saved"]



def test_boot_style_dialogue_snapshot_restore_does_not_claim_saved_session():
    memory = DialogueMemory(SimpleNamespace())
    memory.state.last_topic = "الحضارات القديمة"
    snapshot = memory.snapshot()

    restored = DialogueMemory(SimpleNamespace())
    assert restored.restore_snapshot(snapshot, explicit_saved_session=False) is True
    assert restored.active_restored_session() is None


def test_explicit_saved_dialogue_restore_activates_only_the_selected_session():
    memory = DialogueMemory(SimpleNamespace())
    memory.state.last_topic = "الفن التجريدي"
    snapshot = memory.snapshot()

    restored = DialogueMemory(SimpleNamespace())
    assert restored.restore_snapshot(snapshot, explicit_saved_session=True) is True
    active = restored.active_restored_session()
    assert active["session_id"] == snapshot["session_id"]
    assert active["topic"] == "الفن التجريدي"



def _artwork_session_fixture():
    sid = "artwork-session-fixture"
    return {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid,
                    "exchange_id": "art-step-1",
                    "timestamp": "2026-11-01T10:00:00",
                    "target": "تنفيذ لوحة بالجبس",
                    "user": "استخدمت إطارًا خشبيًا للوحة قديمة وصببت الجبس داخله بسماكة تقارب ثلاثة سنتيمترات.",
                    "assistant": "يمكن ترك الجبس حتى يجف قبل تشكيل سطحه.",
                },
                {
                    "session_id": sid,
                    "exchange_id": "art-step-2",
                    "timestamp": "2026-11-01T10:05:00",
                    "target": "تنفيذ لوحة بالجبس",
                    "user": "بعد الجفاف شكلت السطح بسكين ومفك براغٍ وملعقة.",
                    "assistant": "يمكنك استخدام الأدوات المتاحة لتكوين التضاريس.",
                },
                {
                    "session_id": sid,
                    "exchange_id": "art-step-3",
                    "timestamp": "2026-11-01T10:10:00",
                    "target": "تنفيذ لوحة بالجبس",
                    "user": "دهنت العمل كله بالأسود الغامق ثم أضفت الذهبي والأبيض والأزرق بدرجات متناسقة.",
                    "assistant": "يمكن توزيع الألوان على طبقات بعد جفاف الطلاء الأساسي.",
                },
                {
                    "session_id": sid,
                    "exchange_id": "art-step-4",
                    "timestamp": "2026-11-01T10:15:00",
                    "target": "تنفيذ لوحة بالجبس",
                    "user": "استخدمت صباغة مائية صديقة للبيئة بمظهر عتيق، ثم وضعت طبقة حماية أخيرة أسميها كولا تشبه الورنيش الخشبي الشفاف.",
                    "assistant": "تعمل طبقة الورنيش الشفاف على حماية السطح النهائي.",
                },
            ],
        },
    }


def test_novel_paraphrased_question_retrieves_the_final_protective_layer():
    evidence = retrieve_dialogue_evidence(
        _artwork_session_fixture(),
        "ما المادة الشفافة التي وضعتها في النهاية لحماية العمل؟",
    )

    assert evidence
    assert any(
        item["exchange_id"] == "art-step-4"
        and "كولا" in item["user"]
        and "الورنيش الخشبي الشفاف" in item["user"]
        for item in evidence
    )


def test_novel_questions_retrieve_evidence_across_different_topic_domains():
    sessions_and_questions = [
        (
            {
                "session_id": "film-topic",
                "dialogue_state": {
                    "session_id": "film-topic",
                    "exchange_archive": [{
                        "session_id": "film-topic",
                        "exchange_id": "film-1",
                        "user": "أفضّل أفلام الخيال العلمي التي تعتمد على ألغاز زمنية ولا تكشف النهاية مبكرًا.",
                        "assistant": "يمكن أن تناسبك الأفلام ذات السرد غير الخطي.",
                    }],
                },
            },
            "ما نوع الأفلام التي أفضلها؟",
            "ألغاز زمنية",
        ),
        (
            {
                "session_id": "history-topic",
                "dialogue_state": {
                    "session_id": "history-topic",
                    "exchange_archive": [{
                        "session_id": "history-topic",
                        "exchange_id": "history-1",
                        "user": "أرى أن فهم الحاضر يحتاج إلى مقارنة الأحداث الحالية بجذورها التاريخية في الماضي.",
                        "assistant": "يمكن تتبع أثر الأحداث الماضية في تشكيل الحاضر.",
                    }],
                },
            },
            "لماذا أحتاج إلى فهم الماضي؟",
            "جذورها التاريخية",
        ),
        (
            {
                "session_id": "civilizations-topic",
                "dialogue_state": {
                    "session_id": "civilizations-topic",
                    "exchange_archive": [{
                        "session_id": "civilizations-topic",
                        "exchange_id": "civilizations-1",
                        "user": "أريد مقارنة التنظيم الإداري في مصر القديمة وبلاد الرافدين.",
                        "assistant": "يمكن مقارنة الإدارة والاقتصاد والكتابة في الحضارتين.",
                    }],
                },
            },
            "ما الحضارتان اللتان طلبت المقارنة بينهما؟",
            "بلاد الرافدين",
        ),
    ]

    for session, query, expected in sessions_and_questions:
        evidence = retrieve_dialogue_evidence(session, query)
        assert evidence, (query, session["session_id"])
        assert any(expected in item["user"] for item in evidence), (query, evidence)



def test_agent_boot_checkpoint_restore_explicitly_disables_saved_session_ownership(monkeypatch):
    saved = {"session_id": "boot-dialogue-checkpoint"}
    observed = []
    monkeypatch.setattr("lab_v4_dev.memory.session_state.load_session", lambda: saved)
    fake_agent = SimpleNamespace(
        restore_session_snapshot=lambda data, **kwargs: observed.append((data, kwargs)) or True,
    )

    assert Agent.restore_session_context(fake_agent) is True
    assert observed == [(saved, {"explicit_saved_session": False})]



def test_legacy_top_level_exchange_archive_remains_analyzable():
    data = {
        "session_id": "legacy-top-level-session",
        "exchange_archive": [{
            "session_id": "legacy-top-level-session",
            "user": "كنت أفضّل الفن التجريدي.",
            "assistant": "يمكن أن يقوم على الأشكال والألوان.",
        }],
    }

    analysis = analyze_dialogue_session(data)

    assert analysis["session_id"] == "legacy-top-level-session"
    assert analysis["exchange_count"] == 1
    assert any("الفن التجريدي" in item["content"] for item in analysis["user_information"])



def test_orchestrator_rejects_saved_session_intent_when_route_owner_is_not_l_session():
    agent = SimpleNamespace(runtime=None, _meta=SimpleNamespace(get_version=lambda: "test"))
    decision = RouteDecision(
        route="P-TOOL",
        session_scope="none",
        session_ref=None,
        output_kind="none",
        evidence_scope="none",
        provider_allowed=False,
        intent=Intent.SESSION_RESTORE,
    )

    result = Orchestrator(agent).handle(
        "ما الأدوات التي ذكرتها في الجلسة 72؟",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "session_selector": {"kind": "number", "number": 72, "report_mode": "recall"},
        },
        route_decision=decision,
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_saved_session_owner_guard"
    assert result["executed"] is False



def test_orchestrator_rejects_saved_session_continuation_without_saved_evidence_scope():
    agent = SimpleNamespace(runtime=None, _meta=SimpleNamespace(get_version=lambda: "test"))
    decision = RouteDecision(
        route="L-SESSION",
        session_scope="none",
        session_ref=None,
        output_kind="continue_topic",
        evidence_scope="none",
        provider_allowed=False,
        intent=Intent.RESUME,
    )

    result = Orchestrator(agent).handle(
        "تابع من الجلسة 72",
        parsed={
            "intent": Intent.RESUME,
            "session_selector": {"kind": "number", "number": 72, "report_mode": "standard"},
        },
        route_decision=decision,
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_evidence_scope_guard"
    assert result["executed"] is False



def test_saved_dialogue_retrieval_searches_full_transcript_beyond_live_window():
    sid = "long-session"
    old_exchange = {
        "session_id": sid,
        "exchange_id": "old-first-exchange",
        "timestamp": "2026-10-01T08:00:00",
        "user": "ناقشنا مفهومًا فريدًا اسمه مصطلح_قديم_مميز في بداية الجلسة.",
        "assistant": "هذا المصطلح ورد في بداية الحوار.",
    }
    recent = [
        {
            "session_id": sid,
            "exchange_id": f"recent-{number}",
            "timestamp": f"2026-10-01T09:{number:02d}:00",
            "user": f"رسالة حديثة رقم {number}.",
            "assistant": f"رد حديث رقم {number}.",
        }
        for number in range(9, 41)
    ]
    session = {
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": recent[-32:],
            "transcript_archive": [old_exchange, *recent],
        },
    }

    evidence = retrieve_dialogue_evidence(session, "ما المصطلح الذي ناقشناه في بداية الجلسة؟")
    analysis = analyze_dialogue_session(session)

    assert any(item["exchange_id"] == "old-first-exchange" for item in evidence)
    assert analysis["exchange_count"] == 33


def test_restore_snapshot_loads_only_the_last_32_items_from_full_transcript():
    sid = "long-restore-session"
    transcript = [
        {
            "session_id": sid,
            "exchange_id": f"exchange-{number}",
            "user": f"رسالة {number}",
            "assistant": f"رد {number}",
        }
        for number in range(1, 41)
    ]
    memory = DialogueMemory(SimpleNamespace())
    assert memory.restore_snapshot({
        "session_id": sid,
        "exchange_archive": transcript[-32:],
        "transcript_archive": transcript,
    }) is True

    assert len(memory.state.exchange_archive) == 32
    assert memory.state.exchange_archive[0]["exchange_id"] == "exchange-9"
    assert memory.state.exchange_archive[-1]["exchange_id"] == "exchange-40"



def test_empty_full_transcript_field_falls_back_to_legacy_bounded_archive():
    sid = "legacy-empty-transcript"
    exchange = {
        "session_id": sid,
        "exchange_id": "legacy-exchange-1",
        "user": "ذكرت أنني أفضّل الرسم التجريدي.",
        "assistant": "يمكن بناء العمل على اللون والشكل.",
    }
    analysis = analyze_dialogue_session({
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "transcript_archive": [],
            "exchange_archive": [exchange],
        },
    })

    assert analysis["exchange_count"] == 1
    assert any("الرسم التجريدي" in item["content"] for item in analysis["user_information"])



def test_session_72_art_and_relief_plaster_details_are_retrievable_from_raw_evidence():
    sid = "7ccd0498d634430080dcf5d4c27ceb96"
    exchanges = [
        ("مرحبا.", "مرحبًا بك."),
        ("كيف حالك؟", "أنا بخير، كيف حالك؟"),
        ("أريد أن نتحدث عن الفن التجريدي.", "الفن التجريدي يبتعد عن النقل الحرفي للواقع."),
        ("أريد حوارًا وديًا جديدًا، لا استعادة موضوع سابق.", "حسنًا، لنبدأ حوارًا جديدًا."),
        ("ما معنى الفن التجريدي؟", "هو فن يستخدم اللون والشكل والخط للتعبير."),
        ("أريد دمج الفن التجريدي مع النحت أو النقش البارز.", "يمكن الجمع بين التكوين التجريدي والسطح البارز."),
        (
            "سأستخدم أدوات منزلية بسيطة: سكينًا ومفك براغٍ وملعقة.",
            "يمكنك إضافة أدوات أخرى إذا احتجت إلى تفاصيل أدق.",
        ),
        (
            "سأضع إطارًا خشبيًا للوحة قديمة، وأصب الجبس داخله بسماكة نحو 3 سم، "
            "وأتركه يجف ثم أشكله بالسكين والمفك والملعقة. سأطلي العمل كله بالأسود الغامق، "
            "ثم أضيف الذهبي والأبيض والأزرق بدرجات ونسب متناسقة.",
            "يمكن تنفيذ التشكيل بعد جفاف الجبس، ثم توزيع الألوان على السطح.",
        ),
        (
            "أستعمل صباغة مائية صديقة للبيئة ذات مظهر عتيق، ثم أضع طبقة حماية نهائية "
            "أسميها كولا، وهي تشبه الورنيش الخشبي الشفاف.",
            "هذه الطبقة تحمي السطح وتحافظ على مظهره.",
        ),
        ("ما الأدوات والسماكة التي ذكرتها؟", "لا أملك سجلًا كافيًا لتحديد ذلك."),
        ("ما الألوان التي ذكرتها؟", "لا أستطيع تأكيد الألوان."),
        ("ما نوع الطلاء؟", "لا أملك تفاصيل مؤكدة عن الطلاء."),
        ("ما مادة الحماية النهائية؟", "لا أستطيع تحديد المادة من السياق المتاح."),
    ]
    archive = [
        {
            "session_id": sid,
            "exchange_id": f"{sid}:{index}",
            "timestamp": f"2026-10-22T15:{index:02d}:00",
            "target": "الفن التجريدي والنقش البارز بالجبس",
            "user": user_text,
            "assistant": assistant_text,
        }
        for index, (user_text, assistant_text) in enumerate(exchanges, 1)
    ]
    session = {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "last_topic": "الفن التجريدي والنقش البارز بالجبس",
            "transcript_archive": archive,
            "exchange_archive": archive[-8:],
        },
    }

    analysis = analyze_dialogue_session(session)
    tools = retrieve_dialogue_evidence(session, "ما الأدوات التي ذكرتها؟")
    thickness = retrieve_dialogue_evidence(session, "ما سماكة الجبس؟")
    colors = retrieve_dialogue_evidence(session, "ما الألوان التي أضفتها؟")
    paint = retrieve_dialogue_evidence(session, "ما نوع الصباغة؟")
    protection = retrieve_dialogue_evidence(session, "ما مادة الحماية النهائية؟")
    report = format_dialogue_analysis_report(session)

    assert analysis["exchange_count"] == 13
    assert any("سكينًا" in item["user"] and "ملعقة" in item["user"] for item in tools)
    assert any("3 سم" in item["user"] for item in thickness)
    assert any("الذهبي" in item["user"] and "الأزرق" in item["user"] for item in colors)
    assert any("مائية صديقة للبيئة" in item["user"] for item in paint)
    assert any("كولا" in item["user"] and "الورنيش" in item["user"] for item in protection)
    assert any(
        item["speaker"] == "assistant"
        and item["knowledge_type"] == "assistant_suggestion"
        and "أدوات أخرى" in item["content"]
        for item in analysis["assistant_information"]
    )
    assert any("إطارًا خشبيًا" in item["content"] for item in analysis["user_information"])
    assert "معلومات المستخدم المستخرجة" in report
    assert "مساهمات الوكيل واقتراحاته" in report
    assert "3 سم" in report
    assert "كولا" in report



def test_knowledge_cache_invalidates_when_topic_metadata_changes():
    session = _saved_session()
    exchange = session["dialogue_state"]["exchange_archive"][0]
    exchange["knowledge_version"] = 2
    exchange["knowledge"] = extract_exchange_knowledge(
        exchange,
        session_id=session["session_id"],
        exchange_index=0,
    )
    original_topic = exchange["knowledge"][0]["topic_id"]
    assert original_topic == "تنفيذ لوحة بالجبس"

    exchange["target"] = "تركيب نموذج معماري"
    exchange["timestamp"] = "2026-11-02T12:00:00"
    analysis = analyze_dialogue_session(session)

    rebuilt = next(
        item for item in analysis["user_information"]
        if "إطارًا خشبيًا" in item["content"]
    )
    assert rebuilt["topic_id"] == "تركيب نموذج معماري"
    assert rebuilt["timestamp"] == "2026-11-02T12:00:00"


def test_suggestion_acceptance_is_not_inferred_after_an_unrelated_exchange():
    sid = "suggestion-adjacency-session"
    session = {
        "session_id": sid,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid, "exchange_id": "s1",
                    "target": "الفن التجريدي",
                    "user": "كيف أنعم حواف الجبس؟",
                    "assistant": "يمكنك استخدام ورق الصنفرة لتنعيم الحواف.",
                },
                {
                    "session_id": sid, "exchange_id": "s2",
                    "target": "بلاد الرافدين",
                    "user": "لننتقل إلى حضارة بلاد الرافدين.",
                    "assistant": "ازدهرت مدن سومر وأكد في بلاد الرافدين.",
                },
                {
                    "session_id": sid, "exchange_id": "s3",
                    "target": "بلاد الرافدين",
                    "user": "نعم، أكمل.",
                    "assistant": "من أبرز مراكزها أور وأوروك.",
                },
            ],
        },
    }

    analysis = analyze_dialogue_session(session)

    assert not any(item["relation"] == "accepts" for item in analysis["relationships"])



def test_legacy_dialogue_without_timestamps_preserves_archive_order():
    sid = "legacy-ordered-dialogue"
    session = {
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid,
                    "exchange_id": f"{sid}:2",
                    "user": "المرحلة الثانية من النقاش.",
                    "assistant": "رد المرحلة الثانية.",
                },
                {
                    "session_id": sid,
                    "exchange_id": f"{sid}:10",
                    "user": "المرحلة العاشرة من النقاش.",
                    "assistant": "رد المرحلة العاشرة.",
                },
            ],
        },
    }

    analysis = analyze_dialogue_session(session)

    assert analysis["timeline"][0]["exchange_id"] == f"{sid}:2"
    assert analysis["timeline"][1]["exchange_id"] == f"{sid}:10"
    assert analysis["timeline"][0]["exchange_index"] == 1
    assert analysis["timeline"][1]["exchange_index"] == 2



def test_clarification_turn_is_preserved_as_raw_evidence_but_not_as_answer():
    memory = DialogueMemory(SimpleNamespace())
    prompt = "هل تستطيع تحديد المادة التي ذكرتها سابقًا؟"
    memory.update(
        prompt,
        {
            "status": "needs_clarification",
            "text": "هل تقصد المادة المستخدمة في الطلاء أم طبقة الحماية؟",
        },
        mode="CHAT",
        parsed={
            "intent": "personal_chat",
            "conversation_domain": "general",
            "conversation_act": "CASUAL_CONVERSATION",
        },
        context_transition="continue",
    )
    session = {
        "session_id": memory.state.session_id,
        "dialogue_state": memory.snapshot(),
    }

    exchange = memory.state.exchange_archive[-1]
    analysis = analyze_dialogue_session(session)

    assert exchange["response_status"] == "needs_clarification"
    assert exchange["recall_only"] is True
    assert analysis["timeline"][0]["user_text"] == prompt
    assert any(item["content"] == prompt for item in analysis["unresolved_questions"])
    assert retrieve_dialogue_evidence(session, "ما المادة؟") == []
    assert "لم يُحفظ رد موضوعي مكتمل" in format_dialogue_analysis_report(session)


def test_retrieval_combines_evidence_from_distant_exchanges_in_one_session():
    session = _artwork_session_fixture()
    evidence = retrieve_dialogue_evidence(
        session,
        "اجمع وصف قاعدة اللوحة وأدوات تشكيل سطحها في إجابة واحدة.",
    )
    ids = {item["exchange_id"] for item in evidence}
    assert "art-step-1" in ids
    assert "art-step-2" in ids
    assert all(item["session_id"] == session["session_id"] for item in evidence)


def test_later_explicit_correction_links_to_prior_user_fact_with_provenance():
    sid = "correction-provenance-session"
    session = {
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid,
                    "exchange_id": "old-detail",
                    "user": "كانت سماكة طبقة الجبس ثلاثة سنتيمترات.",
                    "assistant": "سجلت هذه السماكة.",
                },
                {
                    "session_id": sid,
                    "exchange_id": "corrected-detail",
                    "user": "بل، التصحيح أن السماكة خمسة سنتيمترات.",
                    "assistant": "تم اعتماد التصحيح.",
                },
            ],
        },
    }
    analysis = analyze_dialogue_session(session)
    correction = next(
        item for item in analysis["user_corrections"]
        if "خمسة سنتيمترات" in item["content"]
    )
    relation = next(
        item for item in analysis["relationships"]
        if item["relation"] == "corrects"
        and item["source_knowledge_id"] == correction["knowledge_id"]
    )
    assert relation["target_knowledge_id"].startswith("old-detail:user:")
    assert relation["evidence_exchange_id"] == "corrected-detail"
    assert correction["source_exchange_id"] == "corrected-detail"


def test_retrieval_never_returns_evidence_from_a_different_session():
    selected = _artwork_session_fixture()
    other = _saved_session()
    evidence = retrieve_dialogue_evidence(
        selected,
        "ما الأدوات التي استعملتها لتشكيل السطح؟",
    )
    assert evidence
    assert all(item["session_id"] == selected["session_id"] for item in evidence)
    assert not any(item["exchange_id"].startswith("exchange-") for item in evidence)


def test_future_prefixed_arabic_verbs_are_classified_as_user_plans():
    from lab_v4_dev.memory.dialogue_knowledge import extract_exchange_knowledge

    sid = "future-plan-classification"
    records = extract_exchange_knowledge(
        {
            "session_id": sid,
            "exchange_id": "future-plan-1",
            "user": "سأصب الجبس داخل الإطار ثم سأتركه حتى يجف.",
            "assistant": "هذه مراحل متتابعة.",
        },
        session_id=sid,
        exchange_index=0,
    )

    planned = [item["content"] for item in records if item["knowledge_type"] == "planned_action"]
    assert "سأصب الجبس داخل الإطار ثم سأتركه حتى يجف." in planned


def test_dialogue_tokenizer_preserves_term_frequency_for_bm25():
    from lab_v4_dev.memory.dialogue_knowledge import _bm25_score, _token_list

    repeated = _token_list("الجبس والجبس يحتاج إلى التجفيف")
    assert repeated.count("جبس") == 2

    once_score = _bm25_score({"جبس"}, ["جبس", "تجفيف"], {"جبس": 1}, 3, 2.0)
    repeated_score = _bm25_score({"جبس"}, ["جبس", "جبس", "تجفيف"], {"جبس": 1}, 3, 2.0)
    assert repeated_score > once_score


def test_assistant_non_answers_are_not_classified_as_dialogue_knowledge():
    from lab_v4_dev.memory.dialogue_knowledge import extract_exchange_knowledge

    sid = "assistant-non-answer-session"
    records = extract_exchange_knowledge(
        {
            "session_id": sid,
            "exchange_id": "non-answer-1",
            "user": "ما الأدوات التي ذكرتها؟",
            "assistant": "لا أملك سجلًا كافيًا لتحديد ذلك.",
        },
        session_id=sid,
        exchange_index=0,
    )

    assistant_records = [item for item in records if item["speaker"] == "assistant"]
    assert assistant_records
    assert all(item["knowledge_type"] == "assistant_non_answer" for item in assistant_records)


def test_analysis_report_separates_non_answers_from_assistant_knowledge():
    sid = "assistant-non-answer-report"
    session = {
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [{
                "session_id": sid,
                "exchange_id": "non-answer-report-1",
                "user": "ما الأدوات التي ذكرتها؟",
                "assistant": "لا أملك سجلًا كافيًا لتحديد ذلك.",
            }],
        },
    }

    report = format_dialogue_analysis_report(session)

    assert "مساهمات الوكيل واقتراحاته:" in report
    assert "- لا توجد ردود موضوعية محفوظة." in report
    assert "ردود الوكيل غير الموضوعية أو غير المكتملة:" in report
    assert "لا أملك سجلًا كافيًا لتحديد ذلك" in report


def test_unresolved_question_detects_assistant_inability_to_confirm():
    sid = "unresolved-confirmation-session"
    session = {
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [{
                "session_id": sid,
                "exchange_id": "unresolved-confirmation-1",
                "user": "ما مادة الحماية النهائية التي ذكرتها؟",
                "assistant": "لا أستطيع تحديد المادة من السياق المتاح.",
            }],
        },
    }

    analysis = analyze_dialogue_session(session)

    assert any(
        item["source_exchange_id"] == "unresolved-confirmation-1"
        for item in analysis["unresolved_questions"]
    )


def test_correction_can_supersede_a_previously_declared_plan():
    sid = "plan-correction-session"
    session = {
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "exchange_archive": [
                {
                    "session_id": sid,
                    "exchange_id": "plan-old",
                    "target": "صب الجبس",
                    "user": "سأصب الجبس بسماكة ثلاثة سنتيمترات.",
                    "assistant": "تم تسجيل الخطة.",
                },
                {
                    "session_id": sid,
                    "exchange_id": "plan-correction",
                    "target": "صب الجبس",
                    "user": "تصحيح: سأصب الجبس بسماكة خمسة سنتيمترات.",
                    "assistant": "تم تحديث الخطة.",
                },
            ],
        },
    }

    analysis = analyze_dialogue_session(session)
    correction = next(
        item for item in analysis["user_corrections"]
        if "خمسة سنتيمترات" in item["content"]
    )
    relation = next(
        item for item in analysis["relationships"]
        if item["relation"] == "corrects"
        and item["source_knowledge_id"] == correction["knowledge_id"]
    )

    assert relation["target_knowledge_id"].startswith("plan-old:user:")


def test_arabic_definite_and_prepositional_prefixes_share_the_same_token():
    from lab_v4_dev.memory.dialogue_knowledge import _token_list

    variants = _token_list("الجبس بالجبس للجبس والجبس")
    assert variants == ["جبس", "جبس", "جبس", "جبس"]


def test_nonempty_control_only_full_transcript_falls_back_to_legacy_completed_archive():
    sid = "control-only-full-transcript"
    completed = {
        "session_id": sid,
        "exchange_id": "legacy-completed-1",
        "user": "ذكرت أنني أستخدم الجبس في العمل الفني.",
        "assistant": "يمكن تشكيل الجبس بعد جفافه.",
    }
    session = {
        "session_id": sid,
        "dialogue_state": {
            "session_id": sid,
            "transcript_archive": [
                {
                    "session_id": sid,
                    "exchange_id": "boundary-1",
                    "user": "",
                    "assistant": "",
                    "state_boundary_only": True,
                },
                {
                    "session_id": sid,
                    "exchange_id": "clarification-1",
                    "user": "ما المقصود؟",
                    "assistant": "هل يمكنك توضيح السؤال؟",
                    "recall_only": True,
                },
            ],
            "exchange_archive": [completed],
        },
    }

    evidence = retrieve_dialogue_evidence(session, "ما المادة التي أستخدمها؟")
    analysis = analyze_dialogue_session(session)

    assert evidence
    assert evidence[0]["exchange_id"] == "legacy-completed-1"
    assert analysis["exchange_count"] == 2
    assert {item["exchange_id"] for item in analysis["timeline"]} == {
        "clarification-1", "legacy-completed-1",
    }


def test_arabic_ta_marbuta_variants_normalize_for_dialogue_retrieval():
    from lab_v4_dev.memory.dialogue_knowledge import _token_list

    assert _token_list("صباغة صباغه") == ["صباغه", "صباغه"]
