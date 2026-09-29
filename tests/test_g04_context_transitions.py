from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.semantic_contract import ContextTransition
from lab_v4_dev.intent import llm_intent_resolver
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.nlu import context_resolver


STALE_SQL_ENTITY = {
    "action": "cyber_explain",
    "entity": "SQL Injection",
    "entity_type": "CONCEPT",
    "timestamp": 1_790_665_000,
}


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None):
        parsed = dict(parsed or {})
        self.calls.append((text, parsed))
        if parsed.get("intent") == Intent.CYBER_EXPLAIN and not parsed.get("target"):
            return {
                "status": "needs_clarification",
                "intent": parsed.get("intent"),
                "text": "ما الموضوع الذي تريد شرحه؟",
                "source": "test",
            }
        return {
            "status": "success",
            "intent": parsed.get("intent"),
            "target": parsed.get("target"),
            "text": "deterministic response",
            "source": "test",
        }


def configure_offline_nlu(monkeypatch, stale=STALE_SQL_ENTITY):
    getter_calls = []

    def get_stale_entity():
        getter_calls.append(True)
        return dict(stale)

    monkeypatch.setattr(context_resolver, "get_last_entity", get_stale_entity)
    monkeypatch.setattr(context_resolver, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(llm_intent_resolver, "resolve", lambda _text: Intent.UNCLEAR)
    return getter_calls


def test_independent_general_question_is_not_security_framed_or_given_old_history(monkeypatch):
    configure_offline_nlu(monkeypatch)
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    manager = ConversationManager(orchestrator, memory)
    gateway_calls = []

    def offline_gateway(prompt, **kwargs):
        gateway_calls.append({"prompt": prompt, "system": kwargs.get("system", "")})
        return {
            "status": "success",
            "text": "إجابة عامة عن التعلم المستمر.",
            "provider_used": "offline-test",
        }

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        offline_gateway,
    )

    manager.process("اشرح SQL Injection")
    manager.process("اشرح اكثر")
    relevant_history = manager._history_for_transition(
        ContextTransition.CONTINUE,
        {"target": "SQL Injection"},
    )
    assert len(relevant_history) >= 4

    result = manager.process("ما هي أهمية التعلم المستمر؟")

    assert len(orchestrator.calls) == 2
    assert result["source"] == "llm"
    assert result["semantic_request"]["context_transition"] == "explicit_switch"
    assert result["semantic_request"]["requires_context"] is False
    assert memory.last_topic == "أهمية التعلم المستمر؟"
    assert len(gateway_calls) == 1
    prompt_material = gateway_calls[0]["prompt"] + gateway_calls[0]["system"]
    assert "SQL Injection" not in prompt_material
    assert "CSRF" not in prompt_material


def test_incomplete_ambiguous_explanation_does_not_inherit_stale_nlu_topic(monkeypatch):
    getter_calls = configure_offline_nlu(monkeypatch)
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    result = manager.process("اشرح")

    assert result["status"] == "needs_clarification"
    assert result["semantic_request"]["context_transition"] == "ambiguous"
    assert result["semantic_request"]["requires_context"] is False
    assert orchestrator.calls[-1][1]["target"] == ""
    assert memory.last_topic == "SQL Injection"
    assert getter_calls == []


def test_explicit_subject_wins_over_follow_up_shape(monkeypatch):
    configure_offline_nlu(monkeypatch)
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح CSRF")
    result = manager.process("ماذا عن SQL Injection؟")

    assert orchestrator.calls[-1][0] == "ماذا عن SQL Injection؟"
    assert orchestrator.calls[-1][1]["target"] == "SQL Injection"
    assert result["semantic_request"]["context_transition"] == "explicit_switch"
    assert memory.last_topic == "SQL Injection"


def test_g02_explicit_return_then_continuation_keeps_returned_topic(monkeypatch):
    configure_offline_nlu(monkeypatch, stale={
        "action": "cyber_explain",
        "entity": "CSRF",
        "entity_type": "CONCEPT",
        "timestamp": 1_790_665_000,
    })
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    manager.process("اشرح CSRF")
    manager.process("ارجع لشرح SQL Injection")
    result = manager.process("اكمل الشرح")

    assert orchestrator.calls[-1][0] == "SQL Injection اكمل الشرح"
    assert orchestrator.calls[-1][1]["target"] == "SQL Injection"
    assert result["semantic_request"]["context_transition"] == "continue"
    assert memory.last_topic == "SQL Injection"


def test_self_contained_question_without_active_subject_is_new_independent(monkeypatch):
    configure_offline_nlu(monkeypatch)
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    manager = ConversationManager(orchestrator, memory)
    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        lambda _prompt, **_kwargs: {
            "status": "success",
            "text": "إجابة عامة.",
            "provider_used": "offline-test",
        },
    )

    result = manager.process("ما هي أهمية التعلم المستمر؟")

    assert result["source"] == "llm"
    assert result["semantic_request"]["context_transition"] == "new_independent"
    assert result["semantic_request"]["requires_context"] is False
    assert orchestrator.calls == []
