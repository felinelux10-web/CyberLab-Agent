"""Shared Arabic tokenization powers the optional normalized FTS index."""

import sqlite3
from types import SimpleNamespace

from lab_v4_dev.memory.conversation_archive import ConversationArchive
from lab_v4_dev.memory.dialogue_knowledge import _token_list


def test_arabic_alwan_variants_share_one_search_token():
    assert _token_list("ألوان") == ["لون"]
    assert _token_list("الألوان") == ["لون"]
    assert _token_list("اللون") == ["لون"]
    assert _token_list("إطارًا") == _token_list("الإطار") == ["اطار"]
    assert _token_list("خشبيًا") == ["خشبي"]


def test_normalized_fts_rebuild_retrieves_inflection_variant_and_is_repeatable():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    archive = ConversationArchive(SimpleNamespace(conn=connection))
    archive.append_exchange(
        session_id="normalized-fts-session",
        exchange_id="colors-exchange",
        exchange_index=1,
        user_text="أضيف الألوان الذهبية والبيضاء والزرقاء.",
        assistant_text="تم تسجيل الألوان التي ذكرتها.",
        topic="لوحة فنية",
    )

    first = archive.rebuild_normalized_search_index(batch_size=1)
    hits = archive.search_messages(
        "ألوان", session_id="normalized-fts-session", limit=8,
    )
    second = archive.rebuild_normalized_search_index(batch_size=1)
    repeated_hits = archive.search_messages(
        "الألوان", session_id="normalized-fts-session", limit=8,
    )

    assert first["status"] == "completed"
    assert first["indexed_messages"] == 2
    assert first["complete"] is True
    assert hits
    assert any("الألوان" in item["content"] for item in hits)
    assert second["indexed_messages"] == 2
    assert len(repeated_hits) == 2
    assert connection.execute(
        "SELECT COUNT(*) FROM conversation_messages_normalized_fts"
    ).fetchone()[0] == 2
    connection.close()
