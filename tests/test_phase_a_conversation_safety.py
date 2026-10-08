from types import SimpleNamespace


def test_bare_confirmation_has_no_save_intent_without_pending_operation():
    from lab_v4_dev.intent.intent_parser import parse
    from lab_v4_dev.intent.intents import Intent

    result = parse("نعم")
    assert result["intent"] != Intent.SAVE_KB
    assert result["intent"] != Intent.SKIP_KB


def test_bare_confirmation_uses_only_explicit_pending_save_operation():
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.intent.intents import Intent

    context = ContextStore()
    context.last_result = {
        "status": "success",
        "pending_confirmation": {"kind": "save_kb", "topic": "شرح CSRF"},
    }
    calls = []

    class Orchestrator:
        def __init__(self):
            self.context = context

        def handle(self, text, parsed=None, **kwargs):
            calls.append(parsed)
            return {"status": "success", "intent": parsed["intent"], "text": "تم"}

    manager = ConversationManager(Orchestrator(), DialogueMemory(context))
    result = manager.process("نعم")
    assert calls[0]["intent"] == Intent.SAVE_KB
    assert result["intent"] == Intent.SAVE_KB


def test_bare_confirmation_without_pending_operation_stays_conversational():
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.intent.intents import Intent

    context = ContextStore()
    calls = []

    class Orchestrator:
        def __init__(self):
            self.context = context

        def handle(self, *args, **kwargs):
            calls.append(True)
            return {"status": "success", "text": "unexpected"}

    manager = ConversationManager(Orchestrator(), DialogueMemory(context))
    manager._handle_chat = lambda *args, **kwargs: {
        "status": "success", "intent": Intent.PERSONAL_CHAT, "text": "حسنًا"
    }
    result = manager.process("نعم")
    assert result["intent"] == Intent.PERSONAL_CHAT
    assert calls == []


def test_provider_failure_is_not_recorded_as_dialogue_turn(monkeypatch):
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation import conversation_manager as module
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.intent.intents import Intent

    context = ContextStore()

    class Orchestrator:
        def __init__(self):
            self.context = context

        def handle(self, *args, **kwargs):
            raise AssertionError("provider failure test must use chat route")

    manager = ConversationManager(Orchestrator(), DialogueMemory(context))
    monkeypatch.setattr(module, "gateway_ask", lambda *a, **k: {
        "status": "error", "error": {"code": "PROVIDER_FAILURE"}
    })
    result = manager.process("حديث عادي")
    assert result["status"] == "error"
    assert manager.dialogue_memory.last_list == []
