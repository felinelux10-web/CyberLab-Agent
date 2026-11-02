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



def test_session_type_counts_keep_unclassified_records_separate(monkeypatch):
    monkeypatch.setattr(
        session_state,
        "get_session_index",
        lambda: [
            {"session_id": "d1", "session_type": "dialogue"},
            {"session_id": "w1", "session_type": "work"},
            {"session_id": "legacy1", "session_type": "mixed"},
            {"session_id": "legacy2"},
        ],
    )

    assert session_state.get_session_type_counts() == {
        "total": 4,
        "dialogue": 1,
        "work": 1,
        "other": 2,
    }



def test_cyberlab_agent_project_identity_uses_local_project_state(monkeypatch):
    import lab_v4_dev.conversation.conversation_manager as manager_module
    from lab_v4_dev.awareness import project_knowledge

    monkeypatch.setattr(
        project_knowledge,
        "get_project_state",
        lambda: {
            "version": "v5.9.13-dev",
            "current_focus": "Project Knowledge Engine",
            "completed_count": 8,
            "active": ["Event System"],
            "planned": ["Context API"],
        },
    )
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("project identity must be answered locally")
        ),
    )
    context = ContextStore()
    manager = ConversationManager(
        SimpleNamespace(context=context),
        DialogueMemory(context),
    )

    result = manager.process("ماهو cyberlab_agent؟")

    assert result["status"] == "success"
    assert result["source"] == "local_project_identity"
    assert "ليس وصفًا عامًا لمختبر تدريب اختراق" in result["text"]
    assert "v5.9.13-dev" in result["text"]
    assert "Project Knowledge Engine" in result["text"]



def test_finalize_route_freezes_saved_session_owner_and_provider_denial():
    from dataclasses import FrozenInstanceError
    import pytest
    from lab_v4_dev.core.contracts import RouteDecision, SessionRef
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    context = ContextStore()
    manager = ConversationManager(
        SimpleNamespace(context=context),
        DialogueMemory(context),
    )
    decision = manager.finalize_route(
        parsed={"intent": "session_restore", "confidence": 0.95},
        selected_session={
            "kind": "id",
            "session_id": "saved-dialogue-42",
            "output_kind": "summary",
            "topic_filter": "الفن التجريدي",
        },
        saved_session_request=True,
        selected_saved_session_id="saved-dialogue-42",
        transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert isinstance(decision, RouteDecision)
    assert decision.route == "L-SESSION"
    assert decision.session_scope == "saved_id"
    assert decision.session_ref == SessionRef("saved-dialogue-42")
    assert decision.output_kind == "summary"
    assert decision.evidence_scope == "saved_session"
    assert decision.context_lock.active is True
    assert decision.provider_allowed is False
    with pytest.raises(FrozenInstanceError):
        decision.route = "L-LIVE"


def test_finalize_route_keeps_social_turn_local_and_project_facts_off_provider():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition

    context = ContextStore()
    manager = ConversationManager(
        SimpleNamespace(context=context),
        DialogueMemory(context),
    )
    social = manager.finalize_route(
        parsed={
            "intent": "personal_chat",
            "conversation_domain": "social",
            "conversation_act": "SOCIAL_GREETING",
            "confidence": 0.9,
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )
    project = manager.finalize_route(
        parsed={
            "intent": "cyber_explain",
            "conversation_domain": "project",
            "confidence": 0.9,
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert social.route == "L-SOCIAL"
    assert social.provider_allowed is False
    assert project.route == "L-FACT"
    assert project.evidence_scope == "project_state"
    assert project.provider_allowed is False



def test_saved_dialogue_title_uses_latest_substantive_topic_not_social_opener(monkeypatch):
    saved_records = []
    monkeypatch.setattr(session_state, "get_session_index", lambda: [])
    monkeypatch.setattr(session_state, "load_session", lambda: {})
    monkeypatch.setattr(session_state, "_write_session_detail", saved_records.append)
    monkeypatch.setattr(session_state, "_append_recent_archive", lambda data: None)

    session_id = "dialogue-title-topic-test"
    state = {
        "session_id": session_id,
        "last_topic": "مرحبا",
        "history": [],
        "exchange_archive": [
            {
                "session_id": session_id,
                "user": "ناقشنا الفن التجريدي والنقش البارز.",
                "assistant": "تطرقنا إلى التكوين والسطح والفراغ.",
                "target": "الفن التجريدي والنقش البارز",
                "context_kind": "dialogue",
                "conversation_domain": "general",
            },
            {
                "session_id": session_id,
                "user": "مرحبا",
                "assistant": "مرحبًا، كيف يمكنني مساعدتك؟",
                "target": "مرحبا",
                "context_kind": "dialogue",
                "conversation_domain": "social",
            },
        ],
    }

    result = session_state.save_dialogue_checkpoint(dialogue_state=state)

    assert result["title"] == "حوار: الفن التجريدي والنقش البارز"
    assert result["dialogue_state"]["last_topic"] == "الفن التجريدي والنقش البارز"
    assert saved_records
