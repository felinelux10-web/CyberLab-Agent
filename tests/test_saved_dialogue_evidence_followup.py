"""Saved-report factual follow-ups are classified for the canonical session handler."""

from lab_v4_dev.conversation.conversation_manager import ConversationManager


def test_saved_dialogue_detail_classifier_recognizes_factual_questions():
    assert ConversationManager._is_saved_dialogue_detail_question(
        "ما سماكة الجبس؟"
    )
    assert ConversationManager._is_saved_dialogue_detail_question(
        "ما الأدوات التي استعملتها؟"
    )
    assert ConversationManager._is_saved_dialogue_detail_question(
        "ما الألوان التي أضفتها؟"
    )
    assert ConversationManager._is_saved_dialogue_detail_question(
        "ما نوع الصباغة؟"
    )


def test_saved_dialogue_detail_classifier_does_not_capture_general_questions():
    assert not ConversationManager._is_saved_dialogue_detail_question(
        "ما رأيك في الذكاء الاصطناعي؟"
    )
    assert not ConversationManager._is_saved_dialogue_detail_question(
        "ما أهمية التعلم المستمر؟"
    )
    assert not ConversationManager._is_saved_dialogue_detail_question(
        "أريد الانتقال إلى موضوع آخر."
    )



def test_locked_saved_report_routes_detail_question_to_canonical_session_handler():
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.core.contracts import ContextLock
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from types import SimpleNamespace

    saved_id = "saved-dialogue-detail-72"
    memory = DialogueMemory(ContextStore())
    manager = ConversationManager(SimpleNamespace(context=memory.context), memory)
    manager.context_lock = ContextLock(
        active=True,
        session_id=saved_id,
        output_kind="report",
        reason="saved_session_selection",
    )
    manager.active_report_session_id = saved_id
    dispatched = []

    def dispatch(resolved_input, mode, parsed, **kwargs):
        dispatched.append((resolved_input, mode, parsed, kwargs))
        return {
            "status": "success",
            "intent": parsed.get("intent"),
            "source": "test_session_handler",
            "text": "handled by canonical saved-session route",
            "executed": False,
        }

    manager._dispatch = dispatch
    result = manager.process("ما سماكة الجبس؟")

    assert result["status"] == "success"
    assert len(dispatched) == 1
    parsed = dispatched[0][2]
    assert parsed["session_selector"]["session_id"] == saved_id
    assert parsed["session_selector"]["report_mode"] == "recall"
    assert parsed["session_selector"]["output_kind"] == "summary"
    assert parsed["route_decision"].route == "L-SESSION"
    assert parsed["route_decision"].evidence_scope == "saved_session"
    assert parsed["route_decision"].session_ref.session_id == saved_id
