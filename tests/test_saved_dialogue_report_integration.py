import sqlite3
from types import SimpleNamespace

from lab_v4_dev.core.contracts import RouteDecision, SessionRef
from lab_v4_dev.core.orchestrator_handlers.sessions import handle_session_restore
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.memory import session_state
from lab_v4_dev.memory.conversation_archive import ConversationArchive
from lab_v4_dev.memory.dialogue_knowledge import (
    analyze_dialogue_session,
    format_dialogue_analysis_report,
)


def _report_session():
    session_id = "saved-dialogue-report-72"
    exchanges = [
        {
            "session_id": session_id,
            "exchange_id": "report-exchange-1",
            "target": "لوحة جبسية بارزة",
            "user": "أستخدم إطارًا خشبيًا قديمًا لصنع اللوحة.",
            "assistant": "يمكن تثبيت قاعدة العمل داخل الإطار قبل إضافة الجبس.",
        },
        {
            "session_id": session_id,
            "exchange_id": "report-exchange-2",
            "target": "لوحة جبسية بارزة",
            "user": "أصب الجبس بسماكة 3 سم وأنتظر حتى يجف.",
            "assistant": "يمكن الانتظار حتى تجف الطبقة قبل نحت التفاصيل.",
        },
        {
            "session_id": session_id,
            "exchange_id": "report-exchange-3",
            "target": "لوحة جبسية بارزة",
            "user": "أشكّل السطح بسكين ومفك براغ وملعقة.",
            "assistant": "يمكن تجربة أدوات مختلفة للحصول على relief متنوع.",
        },
        {
            "session_id": session_id,
            "exchange_id": "report-exchange-4",
            "target": "لوحة جبسية بارزة",
            "user": "أضع طبقة أساس سوداء ثم أضيف الذهبي والأبيض والأزرق.",
            "assistant": "يمكن توزيع الألوان بتدرجات متناسقة.",
        },
        {
            "session_id": session_id,
            "exchange_id": "report-exchange-5",
            "target": "لوحة جبسية بارزة",
            "user": "أستعمل صباغة مائية ثم أضع طبقة حماية شفافة تشبه ورنيش الخشب.",
            "assistant": "هذه الطبقة تحمي السطح النهائي.",
        },
    ]
    return {
        "session_id": session_id,
        "session_type": "dialogue",
        "title": "لوحة جبسية بارزة",
        "dialogue_state": {
            "session_id": session_id,
            "last_topic": "لوحة جبسية بارزة",
            "exchange_archive": exchanges,
            "transcript_archive": exchanges,
        },
    }


def test_full_saved_dialogue_report_uses_original_exchanges_and_exact_session_scope(monkeypatch):
    session = _report_session()
    session_id = session["session_id"]
    monkeypatch.setattr(session_state, "get_session_index", lambda: [session])
    monkeypatch.setattr(
        session_state, "get_session_by_number",
        lambda number: session if number == 72 else {},
    )
    monkeypatch.setattr(
        session_state, "get_session_by_id",
        lambda value: session if value == session_id else {},
    )
    monkeypatch.setattr(session_state, "load_session", lambda: {})
    monkeypatch.setattr(
        session_state, "recoverable_work_checkpoint", lambda _record: None
    )

    decision = RouteDecision(
        route="L-SESSION",
        session_scope="saved_number",
        session_ref=SessionRef(session_id=session_id, number=72),
        output_kind="report",
        evidence_scope="saved_session",
        provider_allowed=False,
        intent=Intent.SESSION_RESTORE,
    )
    result = handle_session_restore(
        SimpleNamespace(services=SimpleNamespace()),
        Intent.SESSION_RESTORE,
        raw="اكتب تقريرًا تحليليًا عن الجلسة رقم 72",
        route_decision=decision,
        session_selector={
            "kind": "number",
            "number": 72,
            "report_mode": "full",
            "output_kind": "report",
        },
    )

    assert result["status"] == "success", result
    assert result["source"] == "saved_session_report"
    assert result["session_id"] == session_id
    assert result["evidence_exchange_ids"] == [
        "report-exchange-1", "report-exchange-2", "report-exchange-3",
        "report-exchange-4", "report-exchange-5",
    ]
    assert "معلومات المستخدم المستخرجة" in result["text"]
    assert "مساهمات الوكيل واقتراحاته" in result["text"]
    assert "إطارًا خشبيًا" in result["text"]
    assert "3 سم" in result["text"]
    assert "مفك براغ" in result["text"]
    assert "طبقة حماية شفافة" in result["text"]
    assert result["provider_synthesis_attempted"] is False


def test_user_requests_are_not_misreported_as_user_facts_and_report_sources_are_visible():
    session_id = "dialogue-request-fact-separation"
    session = {
        "session_id": session_id,
        "session_type": "dialogue",
        "dialogue_state": {
            "session_id": session_id,
            "exchange_archive": [{
                "session_id": session_id,
                "exchange_id": "request-source-1",
                "target": "تشكيل الجبس",
                "user": "اشرح لي كيفية تشكيل الجبس بعد الجفاف.",
                "assistant": "يمكنك تشكيل السطح بأداة يدوية مناسبة.",
            }],
        },
    }

    analysis = analyze_dialogue_session(session)
    report = format_dialogue_analysis_report(session)

    assert analysis["user_requests"]
    assert all(item["knowledge_type"] == "user_request" for item in analysis["user_requests"])
    assert not any(
        item["knowledge_type"] == "user_request"
        for item in analysis["user_information"]
    )
    assert "طلبات المستخدم" in report
    assert "request-source-1" in report
    assert "الثقة" in report

def test_saved_report_accepts_nested_dialogue_id_only_with_consistent_provenance(monkeypatch):
    session = _report_session()
    saved_id = "saved-checkpoint-72"
    dialogue_id = "live-dialogue-72"
    session["session_id"] = saved_id
    dialogue = session["dialogue_state"]
    dialogue["session_id"] = dialogue_id
    for archive_name in ("transcript_archive", "exchange_archive"):
        for exchange in dialogue[archive_name]:
            exchange["session_id"] = dialogue_id
            exchange["context_kind"] = "dialogue"
            exchange["conversation_domain"] = "general"

    monkeypatch.setattr(session_state, "get_session_index", lambda: [session])
    monkeypatch.setattr(
        session_state, "get_session_by_number",
        lambda number: session if number == 72 else {},
    )
    monkeypatch.setattr(
        session_state, "get_session_by_id",
        lambda value: session if value == saved_id else {},
    )
    monkeypatch.setattr(session_state, "load_session", lambda: {})
    monkeypatch.setattr(
        session_state, "recoverable_work_checkpoint", lambda _record: None
    )

    decision = RouteDecision(
        route="L-SESSION",
        session_scope="saved_number",
        session_ref=SessionRef(session_id=saved_id, number=72),
        output_kind="report",
        evidence_scope="saved_session",
        provider_allowed=False,
        intent=Intent.SESSION_RESTORE,
    )
    result = handle_session_restore(
        SimpleNamespace(services=SimpleNamespace()),
        Intent.SESSION_RESTORE,
        raw="اكتب تقريرًا تحليليًا عن الجلسة رقم 72",
        route_decision=decision,
        session_selector={
            "kind": "number",
            "number": 72,
            "report_mode": "full",
            "output_kind": "report",
        },
    )

    assert result["status"] == "success", result
    assert result["session_id"] == saved_id
    assert result["evidence_exchange_ids"] == [
        "report-exchange-1", "report-exchange-2", "report-exchange-3",
        "report-exchange-4", "report-exchange-5",
    ]
    assert "3 سم" in result["text"]
    assert "مفك براغ" in result["text"]
    assert "معرّف الجلسة: live-dialogue-72" in result["text"]
    assert result["provider_synthesis_attempted"] is False

def test_full_saved_report_merges_sqlite_history_beyond_bounded_checkpoint(monkeypatch):
    session = _report_session()
    session_id = session["session_id"]
    dialogue_id = "live-dialogue-sqlite-72"
    session["dialogue_state"]["session_id"] = dialogue_id
    for archive_name in ("transcript_archive", "exchange_archive"):
        for exchange in session["dialogue_state"][archive_name]:
            exchange["session_id"] = dialogue_id
            exchange["context_kind"] = "dialogue"
            exchange["conversation_domain"] = "general"
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    archive = ConversationArchive(SimpleNamespace(conn=connection))

    migration = archive.migrate_legacy_dialogue_sessions([session])
    assert migration["imported_exchanges"] == 5
    new_exchange_id = archive.append_exchange(
        session_id=dialogue_id,
        user_text="أستخدم ورق صنفرة ناعمًا لتسوية بعض الحواف بعد الجفاف.",
        assistant_text="يمكن استخدامه بحذر لتنعيم الحواف دون إزالة تفاصيل البروز.",
        source="conversation",
        intent="personal_chat",
        topic="لوحة جبسية بارزة",
        status="success",
        metadata={"route": "L-LIVE", "evidence_scope": "live_exchanges"},
    )
    failed_exchange_id = archive.append_exchange(
        session_id=dialogue_id,
        user_text="هل يمكنك تأكيد نوع الورنيش؟",
        assistant_text="provider_exception: upstream unavailable",
        source="conversation",
        intent="cyber_explain",
        topic="لوحة جبسية بارزة",
        status="error",
        metadata={
            "route": "P-TOOL",
            "evidence_scope": "none",
            "failure_message": "upstream unavailable",
        },
    )

    monkeypatch.setattr(session_state, "get_session_index", lambda: [session])
    monkeypatch.setattr(
        session_state, "get_session_by_number",
        lambda number: session if number == 72 else {},
    )
    monkeypatch.setattr(
        session_state, "get_session_by_id",
        lambda value: session if value == session_id else {},
    )
    monkeypatch.setattr(session_state, "load_session", lambda: {})
    monkeypatch.setattr(
        session_state, "recoverable_work_checkpoint", lambda _record: None
    )

    decision = RouteDecision(
        route="L-SESSION",
        session_scope="saved_number",
        session_ref=SessionRef(session_id=session_id, number=72),
        output_kind="report",
        evidence_scope="saved_session",
        provider_allowed=False,
        intent=Intent.SESSION_RESTORE,
    )
    result = handle_session_restore(
        SimpleNamespace(services=SimpleNamespace(
            memory=SimpleNamespace(conversations=archive),
        )),
        Intent.SESSION_RESTORE,
        raw="اكتب تقريرًا تحليليًا عن الجلسة رقم 72",
        route_decision=decision,
        session_selector={
            "kind": "number",
            "number": 72,
            "report_mode": "full",
            "output_kind": "report",
        },
    )

    assert result["status"] == "success", result
    assert result["session_id"] == session_id
    assert len(result["evidence_exchange_ids"]) == 7
    assert new_exchange_id in result["evidence_exchange_ids"]
    assert failed_exchange_id in result["evidence_exchange_ids"]
    assert "ورق صنفرة ناعمًا" in result["text"]
    assert "عدد التبادلات الأصلية: 7" in result["text"]
    assert "التبادلات التي تعذر إكمال الرد عليها: 1" in result["text"]

    transcript_decision = RouteDecision(
        route="L-SESSION",
        session_scope="saved_number",
        session_ref=SessionRef(session_id=session_id, number=72),
        output_kind="transcript",
        evidence_scope="saved_session",
        provider_allowed=True,
        intent=Intent.SESSION_RESTORE,
    )
    transcript = handle_session_restore(
        SimpleNamespace(services=SimpleNamespace(
            memory=SimpleNamespace(conversations=archive),
        )),
        Intent.SESSION_RESTORE,
        raw="اعرض النص الكامل للجلسة رقم 72",
        route_decision=transcript_decision,
        session_selector={
            "kind": "number",
            "number": 72,
            "report_mode": "transcript",
            "output_kind": "transcript",
        },
    )

    assert transcript["status"] == "success", transcript
    assert transcript["output_kind"] == "transcript"
    assert len(transcript["evidence_exchange_ids"]) == 7
    assert "أستخدم ورق صنفرة ناعمًا" in transcript["text"]
    assert "حالة الرد: تعذر إكماله" in transcript["text"]
    assert transcript["provider_synthesis_attempted"] is False

