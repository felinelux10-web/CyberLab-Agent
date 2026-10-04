import pytest

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.semantic_contract import build_semantic_request
from lab_v4_dev.intent import intent_cache, intent_parser, llm_intent_resolver
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.nlu import context_resolver


@pytest.fixture
def isolated_parser(monkeypatch):
    """Disable caches, persistent context writes, and provider-based routing."""
    monkeypatch.setattr(intent_cache, "get", lambda *_a, **_k: None)
    monkeypatch.setattr(intent_cache, "save", lambda *_a, **_k: None)
    monkeypatch.setattr(
        llm_intent_resolver,
        "resolve",
        lambda *_a, **_k: Intent.UNCLEAR,
    )
    monkeypatch.setattr(context_resolver, "get_last_entity", lambda: None)
    monkeypatch.setattr(context_resolver, "save_state", lambda *_a, **_k: None)


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {
            "status": "success",
            "intent": (parsed or {}).get("intent"),
            "target": (parsed or {}).get("target"),
            "text": "orchestrator response",
            "source": "test-orchestrator",
        }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ما اسمك؟", Intent.AGENT_IDENTITY),
        ("من أنت؟", Intent.AGENT_IDENTITY),
        ("من أنت كـ CyberLab Agent؟", Intent.AGENT_IDENTITY),
        ("ما الذي تستطيع فعله فعليًا في هذا المشروع؟", Intent.AGENT_CAPABILITIES),
        ("ما وظائف الوكيل؟", Intent.AGENT_CAPABILITIES),
        ("كيف يعمل CyberLab Agent؟", Intent.AGENT_EXECUTION_FLOW),
        (
            "ما هي الطبقات التي تستخدمها أنت عندما تعالج رسالتي؟",
            Intent.AGENT_ARCHITECTURE,
        ),
        (
            "ما هي الطبقات التي تستخدمها فعليًا لمعالجة رسالتي؟",
            Intent.AGENT_ARCHITECTURE,
        ),
        ("ما هي البنية التي تستخدمها أنت لمعالجة الرسائل؟", Intent.AGENT_ARCHITECTURE),
        ("كيف تعمل عندما أرسل لك رسالة؟", Intent.AGENT_EXECUTION_FLOW),
        (
            "ماذا يحدث لرسالتي من لحظة إدخالها حتى ظهور الرد؟",
            Intent.AGENT_EXECUTION_FLOW,
        ),
        ("ما الذي لا تستطيع تنفيذه؟", Intent.AGENT_LIMITS),
    ],
)
def test_parser_resolves_agent_self_queries_to_canonical_intents(
    isolated_parser, text, expected
):
    result = intent_parser.parse(text)

    assert result["intent"] == expected
    assert result["conversation_domain"] == "agent_self"
    assert result["conversation_act"] in {
        "ASSISTANT_IDENTITY_QUERY",
        "ASSISTANT_CAPABILITY_QUERY",
        "AGENT_ARCHITECTURE_QUERY",
        "AGENT_EXECUTION_FLOW_QUERY",
        "AGENT_LIMITS_QUERY",
    }
    assert result["target"] == ""


def test_agent_self_semantic_request_never_becomes_a_system_action(isolated_parser):
    parsed = intent_parser.parse("ما هي الطبقات التي تستخدمها أنت؟")
    request = build_semantic_request(
        "ما هي الطبقات التي تستخدمها أنت؟",
        "SYSTEM",
        intent=parsed["intent"],
        conversation_domain=parsed["conversation_domain"],
        conversation_act=parsed["conversation_act"],
        confidence=parsed["confidence"],
    )

    assert request.action_type == "none"
    assert request.conversation_domain == "agent_self"
    assert request.intent == Intent.AGENT_ARCHITECTURE


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ما هي بنية مشروع CyberLab Agent؟", Intent.PROJECT_SCAN),
        ("ما هي بنية المشروع؟", Intent.PROJECT_SCAN),
        ("كيف تعمل طبقة Gateway؟", Intent.ARCHITECTURE),
        ("كيف يعمل النظام؟", Intent.ARCHITECTURE),
        ("كيف تعمل SQL Injection؟", Intent.CYBER_EXPLAIN),
        ("ما حالة النظام؟", Intent.SYSTEM_STATUS),
        ("هل النظام يعمل؟", Intent.HEALTH),
        ("ما هو النظام الذي أنت عليه؟", Intent.AGENT_ARCHITECTURE),
        ("كيف يعمل الوكيل؟", Intent.AGENT_EXECUTION_FLOW),
        ("ما حالة الوكيل؟", Intent.STATUS),
        ("هل نستطيع التحدث بشكل عادي؟", Intent.PERSONAL_CHAT),
    ],
)
def test_project_system_cyber_and_social_subjects_remain_distinct(
    isolated_parser, text, expected
):
    result = intent_parser.parse(text)
    assert result["intent"] == expected
    if expected == Intent.PERSONAL_CHAT:
        assert result["conversation_domain"] == "social"


def test_generic_nouns_and_how_alone_do_not_create_status(isolated_parser):
    from lab_v4_dev.intent.keyword_families import match_family

    for text in ("وكيل", "نظام", "كيف"):
        assert match_family(text) != Intent.STATUS
        assert intent_parser.parse(text)["intent"] not in {
            Intent.STATUS,
            Intent.SYSTEM_STATUS,
        }


def test_llm_intent_vocabulary_uses_canonical_self_and_project_values():
    canonical_values = {
        value
        for name, value in vars(Intent).items()
        if name.isupper() and isinstance(value, str)
    }
    assert set(llm_intent_resolver.VALID_INTENTS) == canonical_values
    assert Intent.AGENT_IDENTITY in llm_intent_resolver.VALID_INTENTS
    assert Intent.AGENT_CAPABILITIES in llm_intent_resolver.VALID_INTENTS
    assert Intent.AGENT_ARCHITECTURE in llm_intent_resolver.VALID_INTENTS
    assert Intent.AGENT_EXECUTION_FLOW in llm_intent_resolver.VALID_INTENTS
    assert Intent.AGENT_LIMITS in llm_intent_resolver.VALID_INTENTS
    assert Intent.ARCHITECTURE in llm_intent_resolver.VALID_INTENTS
    assert Intent.MODULES in llm_intent_resolver.VALID_INTENTS
    assert Intent.EXECUTION_FLOW in llm_intent_resolver.VALID_INTENTS
    assert Intent.PROJECT_PURPOSE in llm_intent_resolver.VALID_INTENTS
    from lab_v4_dev.llm.router import needs_llm

    assert needs_llm(Intent.ARCHITECTURE)
    assert needs_llm(Intent.MODULES)
    assert needs_llm(Intent.EXECUTION_FLOW)


def test_self_description_is_grounded_and_uses_chat_not_orchestrator(
    isolated_parser, monkeypatch
):
    monkeypatch.setattr(conversation_module, "detect_mode", lambda _text: "SYSTEM")
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(
        orchestrator,
        DialogueMemory(ContextStore()),
    )
    gateway_calls = []

    def fake_gateway(prompt, **kwargs):
        gateway_calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": "أنا CyberLab Agent، وهذه خلاصة البنية الموثقة.",
            "provider_used": "test-provider",
        }

    monkeypatch.setattr(conversation_module, "gateway_ask", fake_gateway)
    result = manager.process("من أنت كـ CyberLab Agent؟")

    assert result["status"] == "success"
    assert result["intent"] == Intent.AGENT_IDENTITY
    assert result["executed"] is False
    assert result["semantic_request"]["action_type"] == "none"
    assert result["semantic_request"]["context_transition"] == "new_independent"
    assert orchestrator.calls == []
    assert len(gateway_calls) == 1
    assert gateway_calls[0][1]["max_tokens"] == 4000
    system = gateway_calls[0][1]["system"]
    assert "حقائق self-knowledge الموثقة" in system
    assert "lab_v4_dev/core/agent.py" in system
    assert "PreparedExecutionRequest" in system
    assert "المسار الوحيد لكل استدعاء EventLoop" in system
    assert "لا تستنتج وجود نموذج محلي" in system
    assert "Transformer" not in system
    assert "tokenizer" not in system


def test_social_chat_keeps_standard_budget_without_self_knowledge(
    isolated_parser, monkeypatch
):
    monkeypatch.setattr(conversation_module, "detect_mode", lambda _text: "CHAT")
    manager = ConversationManager(
        RecordingOrchestrator(),
        DialogueMemory(ContextStore()),
    )
    gateway_calls = []

    def fake_gateway(prompt, **kwargs):
        gateway_calls.append((prompt, kwargs))
        return {"status": "success", "text": "أهلًا بك.", "provider_used": "test"}

    monkeypatch.setattr(conversation_module, "gateway_ask", fake_gateway)
    result = manager.process("مرحبًا")

    assert result["status"] == "success"
    assert len(gateway_calls) == 1
    assert gateway_calls[0][1]["max_tokens"] == 1600
    assert "حقائق self-knowledge الموثقة" not in gateway_calls[0][1]["system"]


def test_self_knowledge_builder_rejects_non_self_intents():
    from lab_v4_dev.awareness.agent_self_knowledge import build_agent_self_knowledge

    assert build_agent_self_knowledge(Intent.PROJECT_SCAN) == ""
    assert "ConversationManager.process" in build_agent_self_knowledge(
        Intent.AGENT_EXECUTION_FLOW
    )


def test_self_query_starts_independent_of_previous_technical_topic(
    isolated_parser, monkeypatch
):
    memory = DialogueMemory(ContextStore())
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(orchestrator, memory)
    gateway_calls = []

    def fake_gateway(prompt, **kwargs):
        gateway_calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": "أنا CyberLab Agent في هذا المشروع.",
            "provider_used": "test-provider",
        }

    monkeypatch.setattr(conversation_module, "gateway_ask", fake_gateway)
    first = manager.process("اشرح SQL Injection")
    assert memory.last_topic == "SQL Injection"
    self_result = manager.process("من أنت كـ CyberLab Agent؟")

    assert first["intent"] == Intent.CYBER_EXPLAIN
    assert self_result["intent"] == Intent.AGENT_IDENTITY
    assert self_result["semantic_request"]["context_transition"] == "new_independent"
    assert len(orchestrator.calls) == 1
    assert len(gateway_calls) == 1
    assert "SQL Injection" not in gateway_calls[0][0]
