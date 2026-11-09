from types import SimpleNamespace

from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.memory import session_state
from lab_v4_dev.memory.dialogue_knowledge import (
    analyze_dialogue_session,
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
    assert exchange["knowledge_version"] == 1
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
