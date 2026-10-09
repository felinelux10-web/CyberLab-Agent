import json
import os


def _access(requester="explicit_user_command", scope="communication"):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryAccess
    return PersonalMemoryAccess(requester=requester, purpose="test", scope=scope)


def test_personal_memory_category_must_match_access_scope(tmp_path):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryStore

    store = PersonalMemoryStore(str(tmp_path / "private" / "memory.json"))
    assert not store.remember("x", "secret", category="projects", access=_access(scope="communication"))
    assert not (tmp_path / "private" / "memory.json").exists()


def test_personal_memory_cannot_delete_record_from_other_category(tmp_path):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryStore

    path = tmp_path / "private" / "memory.json"
    store = PersonalMemoryStore(str(path))
    assert store.remember("style", "concise", category="communication", access=_access())
    assert not store.forget("style", access=_access(scope="projects"))
    assert store.get_preferences(category="communication", access=_access()) == {"style": "concise"}


def test_personal_memory_write_failure_reports_false_and_preserves_file(monkeypatch, tmp_path):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryStore

    path = tmp_path / "memory.json"
    store = PersonalMemoryStore(str(path))
    assert store.remember("style", "concise", category="communication", access=_access())
    original = path.read_text(encoding="utf-8")
    monkeypatch.setattr(store, "_save", lambda data: (_ for _ in ()).throw(OSError("disk full")))
    assert not store.remember("new", "value", category="communication", access=_access())
    assert path.read_text(encoding="utf-8") == original


def test_personal_memory_corrupt_json_is_not_reported_as_success(tmp_path):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryStore

    path = tmp_path / "memory.json"
    path.write_text("{not-json", encoding="utf-8")
    store = PersonalMemoryStore(str(path))
    assert store.get_preferences(category="communication", access=_access()) == {}
    assert not store.remember("x", "value", category="communication", access=_access())
    assert not store.forget("x", access=_access())


def test_personal_memory_file_and_directory_permissions_are_restricted(tmp_path):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryStore

    path = tmp_path / "private" / "memory.json"
    store = PersonalMemoryStore(str(path))
    assert store.remember("style", "concise", category="communication", access=_access())
    assert os.stat(path.parent).st_mode & 0o777 == 0o700
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_personal_memory_audit_has_operation_scope_and_no_values(tmp_path):
    from lab_v4_dev.memory.personal_memory import PersonalMemoryStore

    store = PersonalMemoryStore(str(tmp_path / "memory.json"))
    assert store.remember("style", "SYNTHETIC_PRIVATE_VALUE", category="communication", access=_access())
    events = store.audit_events()
    assert events[-1]["operation"] == "remember"
    assert events[-1]["scope"] == "communication"
    assert all("value" not in event and "SYNTHETIC_PRIVATE_VALUE" not in repr(event) for event in events)
