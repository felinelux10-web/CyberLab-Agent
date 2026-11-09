from types import SimpleNamespace

from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
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
