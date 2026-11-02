from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.memory import session_state


def _dialogue(session_id, topic, user_text):
    return {
        "session_id": session_id,
        "session_type": "dialogue",
        "title": topic,
        "dialogue_state": {
            "session_id": session_id,
            "last_topic": topic,
            "exchange_archive": [
                {
                    "session_id": session_id,
                    "user": user_text,
                    "assistant": "ناقشنا عناصر الموضوع والعلاقة بينها.",
                    "target": topic,
                    "context_kind": "dialogue",
                    "conversation_domain": "general",
                }
            ],
        },
    }


def test_repeated_topic_analysis_groups_evidence_across_saved_dialogues(monkeypatch):
    first = _dialogue(
        "saved-art-a",
        "الفن والرسم والنحت والنقش",
        "ما العلاقة بين الفن والرسم والنحت والنقش؟",
    )
    second = _dialogue(
        "saved-art-b",
        "الفن التجريدي والنقش البارز",
        "كيف يلتقي الفن التجريدي مع النقش البارز؟",
    )
    work = {
        "session_id": "work-only",
        "session_type": "work",
        "title": "الفن والنقش",
    }
    records = {
        "saved-art-a": first,
        "saved-art-b": second,
        "work-only": work,
    }
    monkeypatch.setattr(
        session_state,
        "get_session_index",
        lambda: [first, second, work],
    )
    monkeypatch.setattr(
        session_state,
        "get_session_by_id",
        lambda session_id: records.get(session_id, {}),
    )

    result = session_state.analyze_repeated_dialogue_topics()

    assert result
    art = result[0]
    assert art["session_count"] == 2
    assert {item["session_id"] for item in art["sessions"]} == {
        "saved-art-a",
        "saved-art-b",
    }
    assert [item["number"] for item in art["sessions"]] == [1, 2]


def test_saved_dialogue_continuation_uses_selected_archive_without_mutating_live_memory(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module

    saved = _dialogue(
        "saved-art-continuation",
        "الفن التجريدي والنقش البارز",
        "ناقشنا العلاقة بين الفن التجريدي والنقش البارز.",
    )
    monkeypatch.setattr(
        session_state,
        "get_session_by_id",
        lambda session_id: saved if session_id == saved["session_id"] else {},
    )
    calls = []

    def local_continue(text, parsed, semantic, *, history=None, context_entity=None):
        calls.append((text, parsed, semantic, history))
        return {
            "status": "success",
            "intent": parsed["intent"],
            "text": "نستأنف من العلاقة بين التكوين والسطح في النقش البارز.",
            "source": "local_unified_response",
            "executed": False,
        }

    monkeypatch.setattr(manager_module, "answer_local_response", local_continue)
    context = ContextStore()
    memory = DialogueMemory(context)
    manager = ConversationManager(SimpleNamespace(context=context), memory)
    manager.active_report_session_id = saved["session_id"]
    before = memory.snapshot()

    result = manager.process("أكمل من نفس النقطة")

    assert result["status"] == "success"
    assert result["source"] == "saved_dialogue_local_continuation"
    assert result["output_kind"] == "continue_topic"
    assert result["session_id"] == saved["session_id"]
    assert calls
    assert calls[0][1]["target"] == "الفن التجريدي والنقش البارز"
    assert any(
        turn["content"] == "ناقشنا العلاقة بين الفن التجريدي والنقش البارز."
        for turn in calls[0][3]
    )
    assert memory.snapshot() == before
    assert manager.active_report_session_id == saved["session_id"]
