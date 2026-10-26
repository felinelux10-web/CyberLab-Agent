import lab_v4_dev.conversation.conversation_manager as manager_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.local_response_engine import answer_local_social
from lab_v4_dev.nlu.conversation_semantics import classify_conversation_semantics


def test_semantically_classified_greeting_has_a_local_response():
    result = answer_local_social(
        "أهلًا وسهلًا",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_GREETING"},
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["source"] == "local_social_engine"
    assert result["executed"] is False
    assert "مرحبًا" in result["text"]


def test_social_fallback_is_reached_through_conversation_manager():
    result = ConversationManager._local_social_answer(
        "أهلًا وسهلًا",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_GREETING"},
    )

    assert result is not None
    assert result["source"] == "local_social_engine"


def test_knowledge_or_execution_act_does_not_get_a_generic_local_social_reply():
    result = answer_local_social(
        "اشرح آلية التوجيه في المشروع",
        {"intent": "cyber_explain", "conversation_act": "NONE"},
    )

    assert result is None


def test_open_ended_social_phrase_remains_with_conversational_responder():
    parsed = classify_conversation_semantics("لا أعرف ماذا أقول", intent="personal_chat")

    result = answer_local_social("لا أعرف ماذا أقول", parsed)

    assert parsed["conversation_act"] == "CASUAL_CONVERSATION"
    assert result is None


class _LocalOnlyOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("social dialogue must not reach the execution owner")


def test_unambiguous_greeting_does_not_call_gateway_or_orchestrator(monkeypatch):
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unambiguous greeting must be answered locally")
        ),
    )
    orchestrator = _LocalOnlyOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("مرحبا")

    assert result["status"] == "success"
    assert result["source"] == "local_social_engine"
    assert "مرحبًا" in result["text"]
    assert orchestrator.calls == []

def test_local_social_suggestions_use_formal_arabic():
    result = ConversationManager._local_social_answer(
        "اقترح لي بعض المواضيع المثيرة للنقاش",
        {"intent": "personal_chat", "conversation_act": "SOCIAL_FOLLOW_UP"},
    )

    assert result is not None
    assert "هل تتحقق الراحة" in result["text"]
    assert "واش" not in result["text"]
    assert "شنو" not in result["text"]

