from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.semantic_contract import ContextTransition
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.memory import session_state


class _Orchestrator:
    def handle(self, text, parsed=None, **_kwargs):
        return {"status": "success", "text": "orchestrator fallback"}


def _manager():
    memory = DialogueMemory(ContextStore())
    return ConversationManager(_Orchestrator(), memory), memory


def test_latest_saved_session_identity_requests_are_not_rendered_as_reports():
    identity = session_state.session_route_contract(
        "لا أتذكر معرف أو رقم آخر جلسة محفوظة"
    )
    number = session_state.session_route_contract(
        "أنا سألتك فقط عن رقم آخر جلسة محفوظة فقط"
    )

    assert identity["kind"] == "latest"
    assert identity["report_mode"] == "identity"
    assert identity["output_kind"] == "session_identity"
    assert number["kind"] == "latest"
    assert number["report_mode"] == "number"
    assert number["output_kind"] == "session_number"


def test_route_decision_accepts_session_identity_output_and_binds_latest_record(monkeypatch):
    manager, _memory = _manager()
    monkeypatch.setattr(
        session_state, "get_session_index",
        lambda: [{"session_id": "latest-id", "updated_at": "2026-11-14T09:00:00"}],
    )
    selection = session_state.session_route_contract(
        "ما رقم آخر جلسة محفوظة؟"
    )

    decision = manager.finalize_route(
        parsed={"intent": Intent.SESSION_RESTORE, "conversation_domain": "system"},
        selected_session=selection,
        saved_session_request=True,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert decision.route == "L-SESSION"
    assert decision.output_kind == "session_number"
    assert decision.session_ref.session_id == "latest-id"


def test_session_restore_returns_only_requested_latest_session_number(monkeypatch):
    from types import SimpleNamespace
    from lab_v4_dev.core.orchestrator_handlers.sessions import handle_session_restore

    record = {"session_id": "latest-id", "title": "آخر حوار"}
    monkeypatch.setattr(
        session_state, "get_session_index",
        lambda: [{"session_id": "latest-id", "updated_at": "2026-11-14T09:00:00"}],
    )
    monkeypatch.setattr(session_state, "get_session_by_id", lambda session_id: record)

    orchestrator = SimpleNamespace(services=SimpleNamespace(dialogue_memory=None))
    decision = SimpleNamespace(
        route="L-SESSION",
        output_kind="session_number",
        session_ref=SimpleNamespace(session_id="latest-id"),
    )
    result = handle_session_restore(
        orchestrator,
        Intent.SESSION_RESTORE,
        raw="ما رقم آخر جلسة محفوظة؟",
        route_decision=decision,
        session_selector={"kind": "latest", "report_mode": "number"},
    )

    assert result["status"] == "success"
    assert result["session_number"] == 1
    assert result["text"] == "رقم الجلسة المحفوظة الأخيرة: 1."


def test_previous_dialogue_resolver_excludes_live_dialogue_and_keeps_exact_identity(monkeypatch):
    records = {
        "live-id": {
            "session_id": "live-id",
            "session_type": "dialogue",
            "dialogue_state": {"session_id": "live-id"},
            "updated_at": "2026-11-14T09:00:00",
        },
        "saved-id": {
            "session_id": "saved-id",
            "session_type": "dialogue",
            "dialogue_state": {"session_id": "saved-id"},
            "updated_at": "2026-11-13T09:00:00",
        },
        "work-id": {
            "session_id": "work-id",
            "session_type": "work",
            "context_state": {},
            "updated_at": "2026-11-12T09:00:00",
        },
    }
    monkeypatch.setattr(
        session_state, "get_session_index",
        lambda: [records["live-id"], records["saved-id"], records["work-id"]],
    )
    monkeypatch.setattr(
        session_state, "get_session_by_id",
        lambda session_id: records.get(str(session_id), {}),
    )

    selected = session_state.get_previous_saved_dialogue(
        exclude_session_id="live-id",
    )

    assert selected["session_id"] == "saved-id"


def test_route_decision_uses_the_shared_previous_dialogue_identity(monkeypatch):
    manager, memory = _manager()
    memory.state.session_id = "live-id"
    monkeypatch.setattr(
        session_state, "get_previous_saved_dialogue",
        lambda *, exclude_session_id: {
            "session_id": "saved-id"
        } if exclude_session_id == "live-id" else {},
    )

    decision = manager.finalize_route(
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "conversation_domain": "system",
        },
        selected_session={"kind": "previous_dialogue", "output_kind": "summary"},
        saved_session_request=True,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert decision.route == "L-SESSION"
    assert decision.session_ref.session_id == "saved-id"


def test_dialogue_state_preserves_first_and_last_replies_after_history_rollover():
    memory = DialogueMemory(ContextStore())
    for index in range(40):
        memory.state.add_turn(
            role="assistant",
            content=f"assistant-reply-{index}",
            context_kind="dialogue",
        )

    assert len(memory.state.history) == 8
    assert memory.state.first_assistant_response == "assistant-reply-0"
    assert memory.state.last_assistant_response == "assistant-reply-39"

    restored = DialogueMemory(ContextStore())
    assert restored.restore_snapshot(memory.snapshot())
    assert restored.state.first_assistant_response == "assistant-reply-0"
    assert restored.state.last_assistant_response == "assistant-reply-39"

    legacy_snapshot = memory.snapshot()
    legacy_snapshot.pop("first_assistant_response", None)
    legacy_snapshot.pop("last_assistant_response", None)
    legacy_snapshot["transcript_archive"] = [
        {
            "session_id": memory.state.session_id,
            "user": f"user-{index}",
            "assistant": f"assistant-reply-{index}",
        }
        for index in range(40)
    ]
    legacy_restored = DialogueMemory(ContextStore())
    assert legacy_restored.restore_snapshot(legacy_snapshot)
    assert legacy_restored.state.first_assistant_response == "assistant-reply-0"
    assert legacy_restored.state.last_assistant_response == "assistant-reply-39"


def test_direct_last_and_first_assistant_reply_queries_return_exact_replies():
    manager, memory = _manager()
    memory.state.session_id = "live-id"
    memory.state.history = [
        {
            "role": "assistant", "content": "هذا أول رد محفوظ.",
            "session_id": "live-id", "context_kind": "dialogue",
        },
        {
            "role": "assistant", "content": "هذا آخر رد محفوظ.",
            "session_id": "live-id", "context_kind": "dialogue",
        },
    ]
    memory.state.exchange_archive = [
        {
            "user": "السؤال الأول", "assistant": "هذا أول رد محفوظ.",
            "session_id": "live-id", "context_kind": "dialogue",
        },
        {
            "user": "السؤال الثاني", "assistant": "هذا آخر رد محفوظ.",
            "session_id": "live-id", "context_kind": "dialogue",
        },
    ]
    parsed = {"conversation_act": "CONVERSATION_HISTORY_QUERY"}

    last = manager._conversation_history_answer(
        "ما هو آخر رد كتبته أنت", parsed,
    )
    first = manager._conversation_history_answer(
        "ما هو أول رد كتبته أنت", parsed,
    )

    assert last["assistant_response"] == "هذا آخر رد محفوظ."
    assert first["assistant_response"] == "هذا أول رد محفوظ."


def test_live_process_routes_direct_last_reply_query_to_dialogue_memory():
    manager, memory = _manager()
    memory.state.session_id = "live-id"
    memory.state.history = [
        {
            "role": "assistant", "content": "هذا آخر رد محفوظ.",
            "session_id": "live-id", "context_kind": "dialogue",
        },
    ]
    memory.state.exchange_archive = [
        {
            "user": "السؤال السابق", "assistant": "هذا آخر رد محفوظ.",
            "session_id": "live-id", "context_kind": "dialogue",
        },
    ]

    archive_before = [dict(item) for item in memory.state.exchange_archive]
    result = manager.process("ما هو آخر رد كتبته أنت")

    assert result["status"] == "success"
    assert result["source"] == "dialogue_memory"
    assert result["assistant_response"] == "هذا آخر رد محفوظ."
    assert memory.state.exchange_archive == archive_before


def test_agent_self_meta_questions_can_be_owned_by_active_dialogue_context():
    manager, _memory = _manager()

    decision = manager.finalize_route(
        parsed={
            "intent": Intent.AGENT_IDENTITY,
            "conversation_domain": "agent_self",
            "conversation_act": "ASSISTANT_STATE_QUERY",
            "response_attributes": {"dialogue_context_reference": True},
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.CONTINUE,
    )

    assert decision.route == "L-LIVE"


def test_contextual_dialogue_typos_are_corrected_without_rewriting_algorithm_terms():
    assert ConversationManager._correct_contextual_dialogue_typos(
        "لماذا لا تكمل الخوار بطريقة منظمة ومترابطة"
    ) == "لماذا لا تكمل الحوار بطريقة منظمة ومترابطة"
    assert ConversationManager._correct_contextual_dialogue_typos(
        "اريد استكمال الخوار من اهر نقطة كنا نناقشها"
    ) == "اريد استكمال الحوار من آخر نقطة كنا نناقشها"
    assert ConversationManager._correct_contextual_dialogue_typos(
        "اشرح الخوارزمية بالتفصيل"
    ) == "اشرح الخوارزمية بالتفصيل"


def test_social_greeting_to_agent_is_not_routed_as_agent_state_lookup():
    from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics

    semantic = classify_conversation_semantics(
        "مرحبا ايها الوكيل كيف حالك اليوم",
        intent=Intent.AGENT_IDENTITY,
        entity_type="AGENT",
    )
    assert semantic["conversation_act"] == "SOCIAL_GREETING"

    manager, _memory = _manager()
    decision = manager.finalize_route(
        parsed={
            "intent": Intent.AGENT_IDENTITY,
            "conversation_domain": "agent_self",
            "conversation_act": "SOCIAL_GREETING",
        },
        selected_session={"kind": "none"},
        saved_session_request=False,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert decision.route == "L-SOCIAL"
