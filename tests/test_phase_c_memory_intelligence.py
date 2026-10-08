def test_knowledge_base_rejects_unconfirmed_low_quality_and_deduplicates(monkeypatch, tmp_path):
    from lab_v4_dev.awareness import knowledge_base as kb

    path = tmp_path / "knowledge.json"
    monkeypatch.setattr(kb, "_kb_path", lambda: str(path))
    assert kb.store("TCP", "قصير") is False
    answer = "TCP ينشئ الاتصال عبر خطوات منظمة تشمل المصافحة الثلاثية وتبادل الحزم والتحقق من أرقام التسلسل قبل نقل البيانات بأمان واستقرار."
    assert kb.store("TCP three-way handshake", answer, confirmed=True)
    assert kb.store("المصافحة الثلاثية في TCP", answer, confirmed=True)
    assert kb.search("كيف يتم إنشاء اتصال TCP؟") == answer
    data = kb._load()
    assert len(data["records"]) == 1
    assert data["records"][next(iter(data["records"]))]["status"] == "ACTIVE"


def test_personal_memory_requires_authorization_and_deletion_is_secure(monkeypatch, tmp_path):
    from lab_v4_dev.memory.personal_memory import (
        PersonalMemoryAccess, PersonalMemoryStore,
    )

    path = tmp_path / "private" / "personal.json"
    store = PersonalMemoryStore(str(path))
    denied = PersonalMemoryAccess("arbitrary_component", "dump", "communication")
    assert store.remember("style", "concise", category="communication", access=denied) is False
    allowed = PersonalMemoryAccess("explicit_user_command", "save preference", "communication")
    assert store.remember("style", "concise", category="communication", access=allowed)
    assert store.get_preferences(
        category="communication",
        access=PersonalMemoryAccess("response_personalization", "response style", "communication"),
    ) == {"style": "concise"}
    assert store.get_preferences(
        category="work_style",
        access=PersonalMemoryAccess("response_personalization", "wrong scope", "work_style"),
    ) == {}
    assert store.forget("style", access=allowed)
    assert store.get_preferences(
        category="communication",
        access=PersonalMemoryAccess("response_personalization", "response style", "communication"),
    ) == {}
    assert all("value" not in event for event in store.audit_events())


def test_personal_memory_router_has_no_full_dump_api():
    import lab_v4_dev.memory.router as router
    assert not hasattr(router, "get_all_personal_memory")
    assert hasattr(router, "get_personal_preferences")
