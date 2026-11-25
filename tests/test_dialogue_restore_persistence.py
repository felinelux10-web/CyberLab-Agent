"""Integration coverage for resuming and saving into the selected dialogue identity."""

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.memory import session_state


def _successful_dialogue_turn(user_text, assistant_text, target):
    return {
        "status": "success",
        "intent": Intent.PERSONAL_CHAT,
        "text": assistant_text,
        "source": "local_social",
        "target": target,
        "semantic_request": {
            "context_kind": "dialogue",
            "conversation_domain": "social",
            "conversation_act": "CASUAL_CONVERSATION",
            "target": target,
        },
    }


def _update(memory, user_text, assistant_text, target):
    memory.update(
        user_text,
        _successful_dialogue_turn(user_text, assistant_text, target),
        mode="CHAT",
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "target": target,
            "confidence": 0.95,
            "conversation_domain": "social",
            "conversation_act": "CASUAL_CONVERSATION",
        },
    )


def test_restored_dialogue_keeps_identity_and_appends_new_exchanges(tmp_path, monkeypatch):
    import lab_v4_dev.core.project_context as project_context

    monkeypatch.setattr(project_context, "project_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        project_context,
        "project_data_file",
        lambda name: str(tmp_path / name),
    )
    monkeypatch.setattr(session_state, "load_session", lambda: {})

    original = DialogueMemory(ContextStore())
    original.state.session_id = "saved-dialogue-lifecycle-72"
    _update(
        original,
        "أستخدم إطارًا خشبيًا قديمًا.",
        "سأحافظ على هذه المعلومة في سياق الحوار.",
        "لوحة جبسية بارزة",
    )
    first_saved = session_state.save_dialogue_checkpoint(
        dialogue_state=original.snapshot(),
        version="test",
    )
    assert first_saved["session_id"] == "saved-dialogue-lifecycle-72"

    restored = DialogueMemory(ContextStore())
    assert restored.restore_snapshot(
        first_saved["dialogue_state"],
        explicit_saved_session=True,
    )
    assert restored.active_restored_session()["session_id"] == "saved-dialogue-lifecycle-72"

    _update(
        restored,
        "أصب الجبس بسماكة نحو 3 سم.",
        "سجلت سماكة الطبقة كما ذكرتها.",
        "لوحة جبسية بارزة",
    )
    _update(
        restored,
        "أشكل السطح بسكين ومفك وملعقة.",
        "هذه هي الأدوات التي أضفتها إلى السجل.",
        "لوحة جبسية بارزة",
    )

    second_saved = session_state.save_dialogue_checkpoint(
        dialogue_state=restored.snapshot(),
        version="test",
    )
    reloaded = session_state.get_session_by_id("saved-dialogue-lifecycle-72")
    transcript = reloaded["dialogue_state"]["transcript_archive"]

    assert second_saved["session_id"] == "saved-dialogue-lifecycle-72"
    assert reloaded["session_id"] == "saved-dialogue-lifecycle-72"
    assert len(transcript) == 3
    assert [item["exchange_index"] for item in transcript] == [1, 2, 3]
    assert transcript[0]["user"] == "أستخدم إطارًا خشبيًا قديمًا."
    assert transcript[1]["user"] == "أصب الجبس بسماكة نحو 3 سم."
    assert transcript[2]["user"] == "أشكل السطح بسكين ومفك وملعقة."
    assert len({item["exchange_id"] for item in transcript}) == 3
