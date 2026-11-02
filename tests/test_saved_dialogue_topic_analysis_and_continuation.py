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
    with pytest.raises(TypeError):
        decision.metadata["owner"] = "live"


def test_finalize_route_keeps_greetings_local_and_marks_project_facts_as_evidence_first():
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
    assert project.provider_allowed is True



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



def test_orchestrator_rejects_non_owned_route_before_task_chain(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    context = ContextStore()
    manager = ConversationManager(
        SimpleNamespace(context=context),
        DialogueMemory(context),
    )
    social_decision = manager.finalize_route(
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "conversation_domain": "social",
            "conversation_act": "SOCIAL_GREETING",
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )
    orchestrator = Orchestrator(SimpleNamespace(runtime=None), context=context)

    result = orchestrator.handle(
        "شغل الاختبارات ثم احذف الملف",
        parsed={"intent": Intent.PERSONAL_CHAT},
        route_decision=social_decision,
    )

    assert result["status"] == "denied"
    assert result["source"] == "route_decision_handle_guard"



def test_finalize_route_locks_live_branch_and_releases_it_on_independent_turn():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    context = ContextStore()
    memory = DialogueMemory(context)
    memory.state.last_topic = "SQL Injection"
    manager = ConversationManager(SimpleNamespace(context=context), memory)

    continuing = manager.finalize_route(
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "target": "SQL Injection",
            "conversation_domain": "technical",
            "conversation_act": "CONVERSATION_CONTINUATION",
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.CONTINUE,
    )
    independent = manager.finalize_route(
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "conversation_domain": "social",
            "conversation_act": "SOCIAL_GREETING",
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert continuing.session_scope == "live_current"
    assert continuing.evidence_scope == "live_exchanges"
    assert continuing.context_lock.active is True
    assert continuing.context_lock.session_id == memory.state.session_id
    assert continuing.context_lock.topic == "SQL Injection"
    assert independent.session_scope == "none"
    assert independent.context_lock.active is False



def test_finalize_route_requires_live_exchange_evidence_for_history_queries():
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    context = ContextStore()
    memory = DialogueMemory(context)
    manager = ConversationManager(SimpleNamespace(context=context), memory)
    memory.state.exchange_archive.append({
        "session_id": memory.state.session_id,
        "user": "ناقشنا الفن التجريدي.",
        "assistant": "تحدثنا عن التكوين والسطح.",
        "target": "الفن التجريدي",
        "context_kind": "dialogue",
        "conversation_domain": "general",
    })

    with_evidence = manager.finalize_route(
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "conversation_domain": "general",
            "conversation_act": "CONVERSATION_HISTORY_QUERY",
            "output_kind": "chat",
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )
    without_evidence = manager.finalize_route(
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "conversation_domain": "general",
            "conversation_act": "CONVERSATION_HISTORY_QUERY",
            "output_kind": "chat",
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )
    assert with_evidence.session_scope == "live_current"
    assert with_evidence.evidence_scope == "live_exchanges"
    assert with_evidence.context_lock.active is True
    memory.state.exchange_archive.clear()
    without_evidence = manager.finalize_route(
        parsed={
            "intent": Intent.PERSONAL_CHAT,
            "conversation_domain": "general",
            "conversation_act": "CONVERSATION_HISTORY_QUERY",
            "output_kind": "chat",
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )
    assert without_evidence.route == "CLARIFY"
    assert without_evidence.evidence_scope == "none"



def test_dialogue_summary_extracts_project_subject_from_user_question_without_target():
    insight = session_state._dialogue_exchange_insights({
        "user": "ماذا كنا نعمل في مشروع cyberlab_agent يعني اخر تعديلات واخر نقطة توقفنا فيها عمليا؟",
        "assistant": "أخبرني بما تريد أن نناقشه.",
        "target": "",
    })

    assert insight
    assert "آخر تعديلات العمل" in insight[0]
    assert "CyberLab Agent" in insight[0]


def test_dialogue_summary_extracts_procedural_subject_without_structured_target():
    insight = session_state._dialogue_exchange_insights({
        "user": "كيف تعمل النجوم النابضة؟",
        "assistant": "يمكنني توضيح ذلك إذا حددت الجانب الذي تريده.",
        "target": "",
    })

    assert insight
    assert "النجوم النابضة" in insight[0]


def test_dialogue_summary_extracts_file_subject_without_structured_target():
    insight = session_state._dialogue_exchange_insights({
        "user": "ما وظيفة orchestrator.py؟",
        "assistant": "أخبرني بما تريد معرفته.",
        "target": "",
    })

    assert insight
    assert "orchestrator.py" in insight[0]



def test_saved_dialogue_summary_prefers_latest_substantive_archive_topic_over_stale_metadata():
    session_id = "saved-dialogue-latest-topic"
    data = {
        "session_id": session_id,
        "session_type": "dialogue",
        "title": "حوار: موضوع قديم",
        "dialogue_state": {
            "session_id": session_id,
            "last_topic": "موضوع قديم",
            "exchange_archive": [
                {
                    "session_id": session_id,
                    "user": "ناقشنا موضوعًا قديمًا.",
                    "assistant": "تحدثنا عن بدايات الموضوع.",
                    "target": "موضوع قديم",
                    "context_kind": "dialogue",
                    "conversation_domain": "general",
                },
                {
                    "session_id": session_id,
                    "user": "كيف يلتقي الفن التجريدي بالنقش البارز؟",
                    "assistant": "ناقشنا التكوين والسطح والفراغ بوصفها عناصر مشتركة.",
                    "target": "الفن التجريدي والنقش البارز",
                    "context_kind": "dialogue",
                    "conversation_domain": "general",
                },
            ],
        },
    }

    summary = session_state._build_dialogue_session_summary(data, "summary")

    assert "الفن التجريدي والنقش البارز" in summary
    assert "موضوع قديم" not in summary
    assert "التكوين والسطح والفراغ" in summary
