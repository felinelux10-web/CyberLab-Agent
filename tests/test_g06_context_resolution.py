from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.semantic_contract import ContextTransition
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent import intent_cache, llm_intent_resolver
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.nlu import context_resolver


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        parsed = dict(parsed or {})
        self.calls.append({
            "text": text,
            "parsed": parsed,
            "context_resolved": kwargs.get("context_resolved"),
        })
        if parsed.get("intent") == Intent.CYBER_EXPLAIN and not parsed.get("target"):
            return {
                "status": "needs_clarification",
                "intent": parsed.get("intent"),
                "text": "ما الموضوع الذي تريد شرحه؟",
                "source": "orchestrator-test",
            }
        return {
            "status": "success",
            "intent": parsed.get("intent"),
            "target": parsed.get("target"),
            "text": "deterministic response",
            "source": "orchestrator-test",
        }


def isolate_external_semantics(monkeypatch, *, cached_intent=None):
    def forbidden_nlu_read():
        raise AssertionError("dialogue path must not read persisted NLU context")

    monkeypatch.setattr(context_resolver, "get_last_entity", forbidden_nlu_read)
    monkeypatch.setattr(context_resolver, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(
        intent_cache,
        "get",
        lambda text: cached_intent(text) if callable(cached_intent) else cached_intent,
    )
    monkeypatch.setattr(llm_intent_resolver, "resolve", lambda _text: Intent.UNCLEAR)


def build_manager(monkeypatch):
    isolate_external_semantics(monkeypatch)
    memory = DialogueMemory(object())
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(orchestrator, memory)
    return manager, memory, orchestrator


def assert_active(memory, topic):
    active = memory.active_context_entity()
    assert active is not None
    assert active["entity"] == topic


def test_semantic_followup_and_reference_matrix_keeps_active_subject(monkeypatch):
    manager, memory, orchestrator = build_manager(monkeypatch)

    first = manager.process("اشرح SQL Injection")
    assert first["semantic_request"]["context_transition"] == "new_independent"
    assert_active(memory, "SQL Injection")

    matrix = [
        ("اشرح أكثر", "continue"),
        ("بسط الشرح", "continue"),
        ("وضح الفكرة", "reference"),
        ("لماذا؟", "reference"),
        ("كيف يعمل؟", "continue"),
        ("ما دوره؟", "continue"),
        ("أعطني مثالًا", "continue"),
        ("اشرح لي هذا بشكل أبسط", "reference"),
        ("ما المقصود بهذا؟", "reference"),
        ("هذا الأمر", "reference"),
        ("هذه الفكرة", "reference"),
        ("فيه", "reference"),
        ("عليه", "reference"),
        ("الموضوع السابق", "reference"),
    ]

    for text, expected_transition in matrix:
        result = manager.process(text)
        call = orchestrator.calls[-1]
        assert result["semantic_request"]["context_transition"] == expected_transition
        assert call["parsed"]["target"] == "SQL Injection"
        assert result["target"] == "SQL Injection"
        assert result["source"] == "orchestrator-test"
        assert_active(memory, "SQL Injection")


def test_critical_a_followups_b_followup_restore_a_followup_sequence(monkeypatch):
    manager, memory, orchestrator = build_manager(monkeypatch)
    sequence = [
        ("اشرح SQL Injection", "new_independent", "SQL Injection"),
        ("اشرح أكثر", "continue", "SQL Injection"),
        ("أعطني مثالًا", "continue", "SQL Injection"),
        ("اشرح CSRF", "explicit_switch", "CSRF"),
        ("بسط الشرح", "continue", "CSRF"),
        ("ارجع لشرح SQL Injection", "restore", "SQL Injection"),
        ("وضح الفكرة", "reference", "SQL Injection"),
    ]

    for text, expected_transition, expected_topic in sequence:
        result = manager.process(text)
        call = orchestrator.calls[-1]
        assert result["semantic_request"]["context_transition"] == expected_transition
        assert result["semantic_request"]["mode"]
        assert result["intent"] == Intent.CYBER_EXPLAIN
        assert result["target"] == expected_topic
        assert result["source"] == "orchestrator-test"
        assert call["parsed"]["target"] == expected_topic
        assert call["context_resolved"] is True
        assert_active(memory, expected_topic)

    csrf_turn = orchestrator.calls[3]
    assert csrf_turn["text"] == "اشرح CSRF"
    assert "SQL Injection" not in csrf_turn["text"]
    csrf_history = manager._history_for_transition(
        ContextTransition.EXPLICIT_SWITCH,
        {"target": "CSRF"},
    )
    assert all(turn.get("target") == "CSRF" for turn in csrf_history)


def test_pending_topic_restoration_reenters_canonical_lifecycle(monkeypatch):
    manager, memory, orchestrator = build_manager(monkeypatch)
    manager.process("اشرح SQL Injection")
    manager.switch_topic("SQL Injection", "اشرح CSRF")

    assert memory.pending_topic == "SQL Injection"
    result = manager.restore_topic()

    assert result["semantic_request"]["context_transition"] == "restore"
    assert result["target"] == "SQL Injection"
    assert result["topic"] == "SQL Injection"
    assert memory.pending_topic is None
    assert_active(memory, "SQL Injection")
    assert orchestrator.calls[-1]["context_resolved"] is True


def test_no_context_reference_cannot_use_nlu_or_intent_cache_or_context_store(monkeypatch):
    isolate_external_semantics(
        monkeypatch,
        cached_intent=lambda text: (
            Intent.CYBER_EXPLAIN if text == "فيه" else None
        ),
    )
    context = ContextStore()
    context.current_subject = "SQL Injection"
    context.last_target = "SQL Injection"
    context.last_intent = Intent.CYBER_EXPLAIN
    memory = DialogueMemory(context)
    orchestrator = Orchestrator(SimpleNamespace(runtime=None), context=context)
    routed = []

    monkeypatch.setattr(orchestrator, "_pre_handler_policy", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "_apply_profile", lambda result, _intent: result)

    def route(intent, target, context_hint, raw):
        routed.append((intent, target, context_hint, raw))
        return {
            "status": "needs_clarification",
            "intent": intent,
            "text": "ما الموضوع الذي تقصده؟",
        }

    monkeypatch.setattr(orchestrator, "_route", route)
    manager = ConversationManager(orchestrator, memory)

    result = manager.process("فيه")

    assert result["semantic_request"]["context_transition"] == "ambiguous"
    assert result["semantic_request"]["requires_context"] is False
    assert routed == [(Intent.CYBER_EXPLAIN, "", "general", "فيه")]
    assert memory.active_context_entity() is None
    assert memory.last_topic is None


def test_canonical_orchestrator_path_does_not_rebind_context_store_target(monkeypatch):
    isolate_external_semantics(monkeypatch)
    context = ContextStore()
    context.current_subject = "old.py"
    context.current_file = "old.py"
    context.last_target = "old.py"
    memory = DialogueMemory(context)
    orchestrator = Orchestrator(SimpleNamespace(runtime=None), context=context)
    routed = []

    monkeypatch.setattr(orchestrator, "_pre_handler_policy", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "_apply_profile", lambda result, _intent: result)
    monkeypatch.setattr(
        orchestrator,
        "_route",
        lambda intent, target, hint, raw: (
            routed.append((intent, target, hint, raw))
            or {"status": "needs_clarification", "intent": intent, "text": "ما الملف؟"}
        ),
    )
    manager = ConversationManager(orchestrator, memory)

    result = manager.process("اشرح هذا الأمر")

    assert result["semantic_request"]["context_transition"] == "ambiguous"
    assert routed == [(Intent.CYBER_EXPLAIN, "", "general", "اشرح هذا الأمر")]
    assert memory.active_context_entity() is None


def test_context_resolved_path_keeps_explicit_repeat_execution_context(monkeypatch):
    context = ContextStore()
    context.last_target = "saved-result.py"
    context.last_intent = Intent.READ_FILE
    orchestrator = Orchestrator(SimpleNamespace(runtime=None), context=context)
    routed = []

    monkeypatch.setattr(orchestrator, "_pre_handler_policy", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "_apply_profile", lambda result, _intent: result)
    monkeypatch.setattr(
        orchestrator,
        "_route",
        lambda intent, target, hint, raw: (
            routed.append((intent, target, hint, raw))
            or {"status": "success", "intent": intent, "text": "repeated"}
        ),
    )

    orchestrator.handle(
        "كرر",
        parsed={"intent": Intent.READ_FILE, "target": "", "context": "general"},
        context_resolved=True,
    )

    assert routed == [(Intent.READ_FILE, "saved-result.py", "general", "كرر")]


def test_targetless_cyber_explanation_bypasses_response_cache(monkeypatch):
    isolate_external_semantics(monkeypatch)
    cache_calls = []

    def cached_response(intent, target=""):
        cache_calls.append((intent, target))
        return "stale cached explanation about SQL Injection"

    monkeypatch.setattr("lab_v4_dev.intent.response_cache.get", cached_response)
    monkeypatch.setattr("lab_v4_dev.awareness.knowledge_base.search", lambda _raw: None)
    monkeypatch.setattr(
        "lab_v4_dev.core.orchestrator.ask",
        lambda *_a, **_k: {"status": "success", "text": "generic clarification response"},
    )
    monkeypatch.setattr(
        "lab_v4_dev.core.orchestrator.get_active_provider",
        lambda: "offline-test",
    )

    orchestrator = Orchestrator(
        SimpleNamespace(runtime=None),
        context=ContextStore(),
    )
    result = orchestrator._route(
        Intent.CYBER_EXPLAIN,
        "",
        "general",
        "اشرح أكثر",
    )

    assert cache_calls == []
    assert result["text"] == "generic clarification response"
    assert "stale cached explanation" not in result["text"]
