from types import SimpleNamespace

import pytest

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.core import orchestrator as orchestrator_module
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent import intent_cache, intent_parser, llm_intent_resolver
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.nlu import context_resolver


@pytest.fixture
def isolated_nlu(monkeypatch):
    """Keep parser tests deterministic and prevent persistent cache writes."""
    monkeypatch.setattr(intent_cache, "get", lambda _text: None)
    monkeypatch.setattr(llm_intent_resolver, "resolve", lambda _text: Intent.UNCLEAR)
    monkeypatch.setattr(context_resolver, "get_last_entity", lambda: None)
    monkeypatch.setattr(context_resolver, "save_state", lambda *_a, **_k: None)


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **_kwargs):
        parsed = dict(parsed or {})
        self.calls.append((text, parsed))
        return {
            "status": "success",
            "intent": parsed.get("intent"),
            "target": parsed.get("target"),
            "text": "شرح تقني سابق عن الموضوع.",
            "source": "test-orchestrator",
        }


class RecordingDNI:
    def __init__(self):
        self.analyses = []

    def set_conversation_analysis(self, value):
        self.analyses.append(dict(value))


def test_unknown_and_varied_social_messages_do_not_default_to_task():
    greetings = (
        "السلام عليكم",
        "هلا والله",
        "أهلًا وسهلًا",
        "تحية طيبة",
    )
    for text in greetings:
        assert detect_mode(text) == "CHAT"

    assert detect_mode("الجو جميل اليوم") == "CHAT"
    assert detect_mode("كيفك اليوم؟") == "QUESTION"
    assert detect_mode("لو سمحت اكتب برنامجًا يطبع مرحبا") == "TASK"


@pytest.mark.parametrize(
    ("text", "expected_act"),
    [
        ("السلام عليكم", "SOCIAL_GREETING"),
        ("يا هلا فيك", "SOCIAL_GREETING"),
        ("يعطيك العافية", "SOCIAL_ACKNOWLEDGEMENT"),
        ("أشكرك كثيرًا", "SOCIAL_ACKNOWLEDGEMENT"),
        ("كيفك اليوم؟", "ASSISTANT_STATE_QUERY"),
        ("طمنّي عليك", "ASSISTANT_STATE_QUERY"),
        ("تقدر تساعدني؟", "ASSISTANT_CAPABILITY_QUERY"),
        ("بماذا تستطيع مساعدتي؟", "ASSISTANT_CAPABILITY_QUERY"),
        ("من أنت؟", "ASSISTANT_IDENTITY_QUERY"),
        ("مين حضرتك؟", "ASSISTANT_IDENTITY_QUERY"),
        ("وأنت؟", "SOCIAL_FOLLOW_UP"),
        ("إلى اللقاء", "SOCIAL_CLOSING"),
        ("أراك لاحقًا", "SOCIAL_CLOSING"),
        ("ما رأيك بالقهوة؟", "CASUAL_DISCUSSION"),
    ],
)
def test_parser_emits_social_and_agent_self_acts_and_clears_false_targets(
    isolated_nlu, text, expected_act
):
    result = intent_parser.parse(text)

    agent_self_acts = {
        "ASSISTANT_CAPABILITY_QUERY": Intent.AGENT_CAPABILITIES,
        "ASSISTANT_IDENTITY_QUERY": Intent.AGENT_IDENTITY,
    }
    expected_intent = agent_self_acts.get(expected_act, Intent.PERSONAL_CHAT)
    expected_domain = "agent_self" if expected_act in agent_self_acts else "social"

    assert result["intent"] == expected_intent
    assert result["conversation_act"] == expected_act
    assert result["conversation_domain"] == expected_domain
    assert result["target"] == ""


@pytest.mark.parametrize(
    ("text", "expected_act", "attribute", "value"),
    [
        ("بسّط هذا الشرح", "SIMPLIFICATION_REQUEST", "interaction_style", "simplified"),
        ("اشرح لي هذا بشكل أبسط", "SIMPLIFICATION_REQUEST", "interaction_style", "simplified"),
        ("اختصر كلامك", "VERBOSITY_REQUEST", "verbosity", "concise"),
        ("اشرحها بأسلوب أكاديمي", "FORMALITY_REQUEST", "formality", "academic"),
        ("خاطبني بالفصحى", "FORMALITY_REQUEST", "formality", "formal"),
    ],
)
def test_style_requests_are_response_metadata_not_execution_intents(
    isolated_nlu, text, expected_act, attribute, value
):
    result = intent_parser.parse(text)

    assert result["intent"] == Intent.PERSONAL_CHAT
    assert result["conversation_act"] == expected_act
    assert result["response_attributes"][attribute] == value


def test_explicit_executable_request_wins_over_social_wording(isolated_nlu):
    result = intent_parser.parse("لو سمحت اكتب سكريبت يطبع مرحبا")

    assert result["intent"] == Intent.GENERATE_CODE
    assert result["conversation_act"] not in {
        "SOCIAL_GREETING",
        "GENERAL_CHAT",
        "CASUAL_CONVERSATION",
    }


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        ("هل يمكن الرجوع بسهولة", Intent.SELF_DIAGNOSE),
        ("يمكنك اختبار محاكاة هذا التعديل", Intent.SELF_DIAGNOSE),
        ("هل يمكن تحسينه", Intent.ANALYZE_CODE),
        ("هل يمكن تبسيطه", Intent.ANALYZE_CODE),
        ("هل أنت متأكد من هذا", Intent.SELF_DIAGNOSE),
        ("من أين يمكن مهاجمة هذا", Intent.CYBER_EXPLAIN),
        ("ما رأيك في التصميم", Intent.CYBER_EXPLAIN),
        ("هل يمكن أن تشرح أكثر", Intent.CYBER_EXPLAIN),
    ],
)
def test_semantic_social_cues_do_not_hijack_domain_intents(
    isolated_nlu, text, expected_intent
):
    result = intent_parser.parse(text)
    assert result["intent"] == expected_intent


def test_explicit_technical_topic_with_style_reaches_orchestrator_and_formats_reply(
    isolated_nlu, monkeypatch
):
    monkeypatch.setattr(
        "lab_v4_dev.intent.response_cache.get",
        lambda *_a, **_k: pytest.fail("style response must not use response cache"),
    )
    monkeypatch.setattr(
        "lab_v4_dev.awareness.knowledge_base.search",
        lambda *_a, **_k: pytest.fail("style response must not use local cached text"),
    )
    ask_calls = []

    def ask(prompt, **kwargs):
        ask_calls.append((prompt, kwargs))
        return {"status": "success", "text": "شرح أكاديمي عن CSRF."}

    monkeypatch.setattr(orchestrator_module, "ask", ask)
    monkeypatch.setattr(
        orchestrator_module,
        "get_active_provider",
        lambda: "offline-test",
    )
    context = ContextStore()
    orchestrator = Orchestrator(
        SimpleNamespace(runtime=None),
        context=context,
    )
    monkeypatch.setattr(orchestrator, "_pre_handler_policy", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "_apply_profile", lambda result, _intent: result)
    manager = ConversationManager(orchestrator, DialogueMemory(context))

    result = manager.process("اشرح CSRF بأسلوب أكاديمي")

    assert result["status"] == "success"
    assert result["intent"] == Intent.CYBER_EXPLAIN
    assert result["semantic_request"]["target"] == "CSRF"
    assert result["semantic_request"]["conversation_act"] == "FORMALITY_REQUEST"
    assert result["semantic_request"]["response_attributes"]["formality"] == "academic"
    assert len(ask_calls) == 1
    assert "صياغة أكاديمية" in ask_calls[0][1]["system"]


def test_social_turn_preserves_active_topic_and_reaches_chat_gateway(
    isolated_nlu, monkeypatch
):
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    dni = RecordingDNI()
    gateway_calls = []

    def gateway(prompt, **kwargs):
        gateway_calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": "وعليكم السلام، كيف أساعدك؟",
            "provider_used": "offline-test",
        }

    monkeypatch.setattr(conversation_module, "gateway_ask", gateway)
    manager = ConversationManager(orchestrator, memory, dni)

    technical = manager.process("اشرح SQL Injection")
    active_before = memory.active_context_entity()
    social = manager.process("السلام عليكم")

    assert technical["status"] == "success"
    assert social["status"] == "success"
    assert social["semantic_request"]["conversation_act"] == "SOCIAL_GREETING"
    assert len(orchestrator.calls) == 1
    assert len(gateway_calls) == 1
    assert memory.active_context_entity() == active_before
    assert memory.last_topic == "SQL Injection"
    assert dni.analyses[-1]["conversation_act"] == "SOCIAL_GREETING"


def test_style_request_uses_contextual_history_without_reexecuting_topic(
    isolated_nlu, monkeypatch
):
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    gateway_calls = []
    real_parse = intent_parser.parse
    parse_calls = []

    def recording_parse(text, **kwargs):
        parse_calls.append(text)
        return real_parse(text, **kwargs)

    def gateway(prompt, **kwargs):
        gateway_calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": "التفسير المبسط للموضوع.",
            "provider_used": "offline-test",
        }

    monkeypatch.setattr(conversation_module, "parse", recording_parse)
    monkeypatch.setattr(conversation_module, "gateway_ask", gateway)
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    result = manager.process("بسّط هذا الشرح")

    assert len(parse_calls) == 2
    assert len(orchestrator.calls) == 1
    assert len(gateway_calls) == 1
    assert result["semantic_request"]["context_transition"] == "continue"
    assert result["semantic_request"]["conversation_act"] == "SIMPLIFICATION_REQUEST"
    assert result["semantic_request"]["response_attributes"]["interaction_style"] == "simplified"
    assert memory.last_topic == "SQL Injection"
    prompt = gateway_calls[0][0]
    assert "SQL Injection" in prompt
    system = gateway_calls[0][1]["system"]
    assert "لغة مبسطة" in system


def test_topic_switch_and_return_survive_intervening_social_turn(
    isolated_nlu, monkeypatch
):
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(object())
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda _prompt, **_kwargs: {
            "status": "success",
            "text": "إجابة اجتماعية.",
            "provider_used": "offline-test",
        },
    )
    manager = ConversationManager(orchestrator, memory)

    manager.process("اشرح SQL Injection")
    manager.process("كيفك اليوم؟")
    switched = manager.process("اشرح CSRF")
    returned = manager.process("اشرح SQL Injection")

    assert switched["semantic_request"]["context_transition"] == "explicit_switch"
    assert switched["semantic_request"]["conversation_act"] == "TOPIC_SHIFT"
    assert returned["semantic_request"]["context_transition"] == "restore"
    assert returned["semantic_request"]["conversation_act"] == "TOPIC_RETURN"
    assert memory.last_topic == "SQL Injection"
    assert len(orchestrator.calls) == 3
