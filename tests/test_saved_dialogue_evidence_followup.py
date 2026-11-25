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
