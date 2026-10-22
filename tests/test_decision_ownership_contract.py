from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent import intent_parser


class Orchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {"status": "success", "text": "تنفيذ غير متوقع"}


def _manager(monkeypatch):
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda *_a, **_k: {
            "status": "success",
            "text": "رد حواري",
            "provider_used": "test",
        },
    )
    orchestrator = Orchestrator()
    memory = DialogueMemory(orchestrator.context)
    return ConversationManager(orchestrator, memory), memory, orchestrator


def test_history_query_has_memory_ownership_before_social_or_ambiguity(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    sid = memory.state.session_id
    memory.state.exchange_archive = [{
        "session_id": sid,
        "user": "ناقشنا موضوع الاستمرارية",
        "assistant": "تحدثنا عن فصل السياقات",
        "target": "الاستمرارية",
        "intent": "personal_chat",
        "context_kind": "dialogue",
        "conversation_domain": "general",
    }]
    before = len(memory.state.exchange_archive)

    result = manager.process("ناذا كنا نقول")

    assert result["source"] == "dialogue_memory"
    assert result["status"] == "success"
    assert result["dialogue_response_mode"] == "summary"
    assert orchestrator.calls == []
    assert len(memory.state.exchange_archive) == before


def test_history_query_with_empty_memory_stays_memory_owned(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)

    result = manager.process("ماذا كنا نقول؟")

    assert result["source"] == "dialogue_memory"
    assert result["status"] == "needs_clarification"
    assert orchestrator.calls == []
    assert len(memory.state.history) == 0


def test_process_uses_one_canonical_parse_for_a_plain_turn(monkeypatch):
    manager, _memory, _orchestrator = _manager(monkeypatch)
    original = intent_parser.parse
    calls = []

    def counted(text, **kwargs):
        calls.append(text)
        return original(text, **kwargs)

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.parse", counted
    )
    result = manager.process("نتحدث عن الذكاء الاصطناعي بشكل عام")

    assert result["status"] == "success"
    assert calls == ["نتحدث عن الذكاء الاصطناعي بشكل عام"]


def test_history_owner_wins_over_a_matching_generic_topic(monkeypatch):
    manager, memory, orchestrator = _manager(monkeypatch)
    memory.state.add_turn(role="user", content="تحدثنا عن الرسم")
    memory.state.add_turn(role="assistant", content="ناقشنا الفن")

    result = manager.process("اكتب ملخص الحوار السابق عن الموضوع")

    assert result["source"] == "dialogue_memory"
    assert orchestrator.calls == []
