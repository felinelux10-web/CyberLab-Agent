import pytest

from lab_v4_dev.awareness.agent_self_knowledge import build_agent_self_knowledge
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent import intent_cache, intent_parser, llm_intent_resolver
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.llm.prompt_builder import build_chat_prompt
from lab_v4_dev.nlu import context_resolver
from lab_v4_dev.nlu.conversation_semantics import classify_agent_self_query


AGENT_INTENTS = frozenset({
    Intent.AGENT_IDENTITY,
    Intent.AGENT_CAPABILITIES,
    Intent.AGENT_ARCHITECTURE,
    Intent.AGENT_EXECUTION_FLOW,
    Intent.AGENT_LIMITS,
})

# Required regression matrix: the same examples are exercised at the semantic,
# canonical-parser, and ConversationManager.process boundaries below.
REPORT_CASES = [
    # Identity
    ("ماهو اسمك", Intent.AGENT_IDENTITY),
    ("من أنت", Intent.AGENT_IDENTITY),
    ("عرف عن نفسك", Intent.AGENT_IDENTITY),
    ("ما هي هويتك", Intent.AGENT_IDENTITY),
    ("ماهيتك أنت", Intent.AGENT_IDENTITY),
    ("صف نفسك", Intent.AGENT_IDENTITY),
    # Capabilities
    ("ماذا تستطيع أن تفعل أنت؟", Intent.AGENT_CAPABILITIES),
    ("ماذا يمكنك أن تفعل داخل هذا المشروع؟", Intent.AGENT_CAPABILITIES),
    ("ما الذي تستطيع فعله أنت فعليًا داخل هذا المشروع؟", Intent.AGENT_CAPABILITIES),
    ("ما قدراتك؟", Intent.AGENT_CAPABILITIES),
    ("ما الذي تقدر عليه؟", Intent.AGENT_CAPABILITIES),
    ("ما هي الوظائف الموجودة فيك حاليًا، وليس قدرات نموذج ذكاء اصطناعي عامة؟", Intent.AGENT_CAPABILITIES),
    # Architecture
    ("ما هي بنيتك أنت؟", Intent.AGENT_ARCHITECTURE),
    ("ما هي معماريتك؟", Intent.AGENT_ARCHITECTURE),
    ("ما هي المكونات التي تستخدمها أنت؟", Intent.AGENT_ARCHITECTURE),
    ("ما هي الطبقات التي تستخدمها لمعالجة رسالتي؟", Intent.AGENT_ARCHITECTURE),
    ("ما هي المكونات البرمجية الفعلية التي تستخدمها لمعالجة رسالتي؟", Intent.AGENT_ARCHITECTURE),
    # Execution flow
    ("كيف تعالج رسالتي؟", Intent.AGENT_EXECUTION_FLOW),
    ("ماذا يحدث عندما أرسل لك سؤالًا؟", Intent.AGENT_EXECUTION_FLOW),
    ("كيف تنتقل رسالتي داخلك إلى الرد؟", Intent.AGENT_EXECUTION_FLOW),
    ("هل كل رسالة تدخل في مسار تنفيذ مهمة؟", Intent.AGENT_EXECUTION_FLOW),
    ("ماذا يحدث عندما أرسل لك سؤالًا عاديًا لا يطلب تنفيذ أي عملية؟", Intent.AGENT_EXECUTION_FLOW),
    # Limits and grounding
    ("ما حدودك أنت؟", Intent.AGENT_LIMITS),
    ("ما الذي لا تستطيع فعله؟", Intent.AGENT_LIMITS),
    ("هل كل ما تقوله عن نفسك مأخوذ من الكود؟", Intent.AGENT_LIMITS),
    ("هل ما تصفه عن بنية CyberLab Agent مثبت في الكود؟", Intent.AGENT_LIMITS),
    (
        "هل كل ما تقوله عن بنية CyberLab Agent مأخوذ من الكود الفعلي، أم أن بعضه معرفة عامة؟",
        Intent.AGENT_LIMITS,
    ),
]

PROJECT_NEGATIVE_CASES = [
    ("ما هي بنية مشروع CyberLab Agent؟", Intent.PROJECT_SCAN),
    ("ما هي طبقات المشروع؟", Intent.PROJECT_SCAN),
    ("ما هي الملفات المهمة في المشروع؟", Intent.DEPENDENCY_MAP),
    ("اشرح معمارية المشروع.", Intent.PROJECT_SCAN),
    ("ما هي مكونات المشروع؟", Intent.PROJECT_SCAN),
    ("افحص بنية المشروع.", Intent.PROJECT_SCAN),
]

EXECUTABLE_NEGATIVE_CASES = [
    ("حلل orchestrator.py", Intent.ANALYZE_CODE),
    ("analyze orchestrator.py", Intent.ANALYZE_CODE),
    ("Can you analyze orchestrator.py?", Intent.ANALYZE_CODE),
    ("هل يمكنك تحليل orchestrator.py؟", Intent.ANALYZE_CODE),
    ("افحص ملفات المشروع", Intent.ANALYZE_CODE),
    ("شغّل الاختبارات", Intent.RUN_TESTS),
    ("run tests", Intent.RUN_TESTS),
    ("هل يمكنك تشغيل الاختبارات؟", Intent.RUN_TESTS),
    ("اقرأ conversation_manager.py", Intent.READ_FILE),
]


@pytest.fixture
def isolated_parser(monkeypatch):
    monkeypatch.setattr(intent_cache, "get", lambda *_a, **_k: None)
    monkeypatch.setattr(intent_cache, "save", lambda *_a, **_k: None)
    monkeypatch.setattr(
        llm_intent_resolver, "resolve", lambda *_a, **_k: Intent.UNCLEAR
    )
    monkeypatch.setattr(context_resolver, "get_last_entity", lambda: None)
    monkeypatch.setattr(context_resolver, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(conversation_module, "detect_mode", lambda _text: "CHAT")


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, parsed, kwargs))
        return {
            "status": "success",
            "intent": (parsed or {}).get("intent"),
            "text": "orchestrator test response",
        }


def manager_with_spies(monkeypatch):
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(ContextStore()))
    gateway_calls = []

    def fake_gateway(prompt, **kwargs):
        gateway_calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": "رد حواري اختباري مؤسس على المصادر.",
            "provider_used": "test-provider",
        }

    monkeypatch.setattr(conversation_module, "gateway_ask", fake_gateway)
    return manager, orchestrator, gateway_calls


@pytest.mark.parametrize(("text", "expected"), REPORT_CASES)
def test_direct_classifier_accepts_all_reported_natural_forms(text, expected):
    signal = classify_agent_self_query(text)

    assert signal is not None
    assert signal["intent"] == expected
    assert signal["conversation_domain"] == "agent_self"


@pytest.mark.parametrize(("text", "expected"), REPORT_CASES)
def test_public_parser_returns_canonical_agent_self_intent(
    isolated_parser, text, expected
):
    result = intent_parser.parse(text)

    assert result["intent"] == expected
    assert result["conversation_domain"] == "agent_self"
    assert result["entity_type"] == "AGENT_SELF"
    assert result["intent"] in AGENT_INTENTS
    assert result["conversation_act"] != result["intent"]


@pytest.mark.parametrize(("text", "expected"), REPORT_CASES)
def test_conversation_manager_routes_agent_self_to_grounded_chat(
    isolated_parser, monkeypatch, text, expected
):
    manager, orchestrator, gateway_calls = manager_with_spies(monkeypatch)

    result = manager.process(text)

    assert result["status"] == "success"
    assert result["intent"] == expected
    assert result["source"] == "llm"
    assert result["text"] == "رد حواري اختباري مؤسس على المصادر."
    assert result["executed"] is False
    assert result["semantic_request"]["action_type"] == "none"
    assert orchestrator.calls == []
    assert len(gateway_calls) == 1
    system = gateway_calls[0][1]["system"]
    assert "حقائق self-knowledge الموثقة" in system
    assert "مصادر الشفرة:" in system
    assert "lab_v4_dev/intent/intents.py" in system
    assert "تمييز" in system and "trace" in system.lower()


@pytest.mark.parametrize(("text", "expected"), PROJECT_NEGATIVE_CASES)
def test_project_questions_remain_project_intents(
    isolated_parser, monkeypatch, text, expected
):
    signal = classify_agent_self_query(text)
    parsed = intent_parser.parse(text)
    manager, orchestrator, gateway_calls = manager_with_spies(monkeypatch)

    result = manager.process(text)

    assert signal is None
    assert parsed["intent"] == expected
    assert parsed["conversation_domain"] != "agent_self"
    assert result["intent"] == expected
    assert not result["intent"] in AGENT_INTENTS
    assert result["executed"] is True
    assert len(orchestrator.calls) == 1
    assert gateway_calls == []


@pytest.mark.parametrize(("text", "expected"), EXECUTABLE_NEGATIVE_CASES)
def test_executable_requests_keep_canonical_intent_and_orchestrator_owner(
    isolated_parser, monkeypatch, text, expected
):
    signal = classify_agent_self_query(text)
    parsed = intent_parser.parse(text)
    manager, orchestrator, gateway_calls = manager_with_spies(monkeypatch)

    result = manager.process(text)

    assert signal is None
    assert parsed["intent"] == expected
    assert parsed["intent"] not in AGENT_INTENTS
    assert result["intent"] == expected
    assert result["executed"] is True
    assert len(orchestrator.calls) == 1
    assert gateway_calls == []


def test_grounded_prompt_separates_architectural_facts_from_runtime_trace():
    knowledge = build_agent_self_knowledge(Intent.AGENT_EXECUTION_FLOW)
    system, _prompt = build_chat_prompt(
        "كيف تعالج رسالتي؟",
        agent_self_knowledge=knowledge,
    )

    assert "حقائق self-knowledge الموثقة" in system
    assert "مصادر الشفرة:" in system
    assert "lab_v4_dev/intent/intents.py" in system
    assert "تمييز بين الحقائق المعمارية وأثر التشغيل" in system
    assert "لا تدّعِ أن الرسالة الحالية سلكت مسارًا بعينه دون trace صريح" in system


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("«ماهو اسمك»!!!", Intent.AGENT_IDENTITY),
        ("عرف عن نفسك...", Intent.AGENT_IDENTITY),
        ("أريد أن تصف نفسك", Intent.AGENT_IDENTITY),
        ("اسمك يا CyberLab", Intent.AGENT_IDENTITY),
        ("ما الذي تستطبع فعله انت", Intent.AGENT_CAPABILITIES),
        ("وش تقدر تسوي", Intent.AGENT_CAPABILITIES),
        ("شو بتقدر تعمل؟", Intent.AGENT_CAPABILITIES),
        ("المكونات اللي تستخدمها لمعالجة رسالتي", Intent.AGENT_ARCHITECTURE),
        ("اشرح لي المسار الفعلي لرسالتي", Intent.AGENT_EXECUTION_FLOW),
        ("كيف تتعامل مع هذه الرسالة قبل الرد", Intent.AGENT_EXECUTION_FLOW),
        ("هل كل ما تقوله عن بنية CyberLab مأخوذ من الكود", Intent.AGENT_LIMITS),
        ("هل كلامك عن بنية CyberLab مبني على الكود أو معرفة عامة", Intent.AGENT_LIMITS),
    ],
)
def test_tolerates_punctuation_colloquial_forms_and_small_typos(
    isolated_parser, text, expected
):
    signal = classify_agent_self_query(text)
    parsed = intent_parser.parse(text)

    assert signal is not None
    assert signal["intent"] == expected
    assert parsed["intent"] == expected


@pytest.mark.parametrize(
    "text",
    [
        "ما هي بنية مشروع CyberLab Agent؟",
        "ما هي ملفات المشروع؟",
        "اشرح لي معمارية المشروع.",
        "ما هي مكونات CyberLab Agent؟",
        "ما هي قدرات مشروع CyberLab Agent؟",
        "حلل بنية المشروع.",
        "ما حالة الوكيل؟",
        "هل نستطيع التحدث باللهجة العامية؟",
    ],
)
def test_project_status_and_social_queries_are_not_agent_self_queries(
    isolated_parser, text
):
    assert classify_agent_self_query(text) is None
    assert intent_parser.parse(text)["intent"] not in AGENT_INTENTS


@pytest.mark.parametrize(
    "text",
    [
        "هل شغّل النظام الاختبارات؟",
        "ما سبب تشغيل الاختبارات؟",
    ],
)
def test_questions_about_test_execution_are_not_run_commands(
    isolated_parser, monkeypatch, text
):
    manager, orchestrator, gateway_calls = manager_with_spies(monkeypatch)

    assert classify_agent_self_query(text) is None
    parsed = intent_parser.parse(text)
    assert parsed["intent"] != Intent.RUN_TESTS

    result = manager.process(text)

    assert result["intent"] != Intent.RUN_TESTS
    assert result["executed"] is False
    assert orchestrator.calls == []
    assert len(gateway_calls) == 1
