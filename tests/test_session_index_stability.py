import json

from lab_v4_dev.memory import session_state


def test_session_index_deduplicates_legacy_ids_without_reordering(tmp_path, monkeypatch):
    archive_path = tmp_path / "session_archive.json"
    archive_path.write_text(
        json.dumps(
            [
                {"session_id": "dialogue-a", "title": "قديم", "updated_at": "2026-10-20"},
                {"session_id": "dialogue-b", "title": "الفن", "updated_at": "2026-10-21"},
                {"session_id": "dialogue-a", "title": "أحدث نسخة", "updated_at": "2026-10-22"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_state, "_archive_file", lambda: str(archive_path))

    index = session_state.get_session_index()

    assert [item["session_id"] for item in index] == ["dialogue-a", "dialogue-b"]
    assert [item["title"] for item in index] == ["أحدث نسخة", "الفن"]


def test_updating_session_metadata_does_not_change_its_number(tmp_path, monkeypatch):
    archive_path = tmp_path / "session_archive.json"
    archive_path.write_text(
        json.dumps(
            [
                {
                    "session_id": "dialogue-a",
                    "title": "الفن",
                    "created_at": "2026-10-20",
                    "updated_at": "2026-10-20",
                },
                {"session_id": "dialogue-b", "title": "التحية", "updated_at": "2026-10-21"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_state, "_archive_file", lambda: str(archive_path))

    session_state._append_recent_archive(
        {
            "session_id": "dialogue-a",
            "session_type": "dialogue",
            "title": "الفن والنقش البارز",
            "updated_at": "2026-10-23",
        }
    )

    index = session_state.get_session_index()
    assert [item["session_id"] for item in index] == ["dialogue-a", "dialogue-b"]
    assert index[0]["title"] == "الفن والنقش البارز"
    assert index[0]["created_at"] == "2026-10-20"


def test_recent_sessions_are_ordered_by_update_time_not_numbering(tmp_path, monkeypatch):
    archive_path = tmp_path / "session_archive.json"
    archive_path.write_text(
        json.dumps(
            [
                {"session_id": "dialogue-a", "updated_at": "2026-10-23"},
                {"session_id": "dialogue-b", "updated_at": "2026-10-21"},
                {"session_id": "dialogue-c", "updated_at": "2026-10-24"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_state, "_archive_file", lambda: str(archive_path))

    recent = session_state.get_recent_sessions()

    assert [item["session_id"] for item in recent] == [
        "dialogue-c",
        "dialogue-a",
        "dialogue-b",
    ]


def test_explicit_saved_session_count_has_a_local_selector():
    assert session_state.session_selector("كم عدد الجلسات المحفوظة؟") == {
        "kind": "count",
        "report_mode": "compact",
    }


def test_other_saved_dialogue_with_topic_routes_to_search():
    selected = session_state.session_selector(
        "في جلسة أخرى كنا نتحدث عن موضوع الفن التجريدي"
    )
    assert selected["kind"] == "search"
    assert "الفن التجريدي" in selected["query"]


def test_partial_topic_search_finds_broader_saved_dialogue_title(tmp_path, monkeypatch):
    archive_path = tmp_path / "session_archive.json"
    archive_path.write_text(
        json.dumps(
            [
                {
                    "session_id": "art-session",
                    "session_type": "dialogue",
                    "title": "حوار: الفن والرسم والنحت والنقش",
                    "topic": "الفن والرسم والنحت والنقش",
                    "active_goal": "الفن والرسم والنحت والنقش",
                    "updated_at": "2026-10-22",
                },
                {
                    "session_id": "greeting-session",
                    "session_type": "dialogue",
                    "title": "حوار: مرحبا",
                    "topic": "مرحبا",
                    "active_goal": "مرحبا",
                    "updated_at": "2026-10-27",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_state, "_archive_file", lambda: str(archive_path))

    results = session_state.search_sessions("الفن التجريدي", limit=5)

    assert results
    assert results[0]["session_id"] == "art-session"
