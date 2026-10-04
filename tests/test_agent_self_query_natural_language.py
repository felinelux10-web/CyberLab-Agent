import pytest

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.intent import intent_cache, intent_parser, llm_intent_resolver
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.nlu import context_resolver
from lab_v4_dev.nlu.conversation_semantics import classify_agent_self_query


REPORT_CASES = [
    ("ماهو اسمك", Intent.AGENT_IDENTITY),
    ("عرف عن نفسك بشكل كامل مثلا من انت و ماهيتك", Intent.AGENT_IDENTITY),
    (
        "أريد أن تصف نفسك أنت، CyberLab Agent الموجود أمامي الآن، "
        "وليس الذكاء الاصطناعي بشكل عام.",
        Intent.AGENT_IDENTITY,
    ),
    ("ما الذي تستطيع فعله أنت فعليًا داخل هذا المشروع؟", Intent.AGENT_CAPABILITIES),
    (
        "ما هي الوظائف الموجودة فيك حاليًا، وليس قدرات نموذج ذكاء اصطناعي عامة؟",
        Intent.AGENT_CAPABILITIES,
    ),
    (
        "ما هي المكونات البرمجية الفعلية التي تستخدمها لمعالجة رسالتي؟",
        Intent.AGENT_ARCHITECTURE,
    ),
    (
        "اشرح لي المسار الفعلي لرسالتي من لحظة إدخالها حتى إنتاج الرد، "
        "بناءً على الكود الموجود في CyberLab Agent.",
        Intent.AGENT_EXECUTION_FLOW,
    ),
    ("هل كل رسالة أرسلها لك تدخل في مسار تنفيذ مهمة؟", Intent.AGENT_EXECUTION_FLOW),
    (
        "ماذا يحدث عندما أرسل لك سؤالًا عاديًا لا يطلب تنفيذ أي عملية؟",
        Intent.AGENT_EXECUTION_FLOW,
    ),
    (
        "اشرح لي باختصار كيف تتعامل مع هذه الرسالة قبل أن تجيب عنها. "
        "لا تنفذ أي عملية.",
        Intent.AGENT_EXECUTION_FLOW,
    ),
    (
        "هل كل ما تقوله عن بنية CyberLab Agent مأخوذ من الكود الفعلي، "
        "أم أن بعضه معرفة عامة؟",
        Intent.AGENT_LIMITS,
    ),
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


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, parsed, kwargs))
        return {"status": "success", "text": "execution path"}


@pytest.mark.parametrize(("text", "expected"), REPORT_CASES)
def test_direct_classifier_accepts_all_reported_natural_forms(text, expected):
    signal = classify_agent_self_query(text)

    assert signal is not None
    assert signal["intent"] == expected
    assert signal["conversation_domain"] == "agent_self"


@pytest.mark.parametrize(("text", "expected"), REPORT_CASES)
def test_public_parser_preserves_the_direct_self_query_classification(
    isolated_parser, text, expected
):
    result = intent_parser.parse(text)

    assert result["intent"] == expected
    assert result["conversation_domain"] == "agent_self"
    assert result["entity_type"] == "AGENT_SELF"


@pytest.mark.parametrize(("text", "expected"), REPORT_CASES)
def test_conversation_runtime_routes_reported_queries_to_grounded_chat(
    isolated_parser, monkeypatch, text, expected
):
    monkeypatch.setattr(conversation_module, "detect_mode", lambda _text: "CHAT")
    orchestrator = RecordingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(ContextStore()))
    gateway_calls = []

    def fake_gateway(prompt, **kwargs):
        gateway_calls.append((prompt, kwargs))
        return {
            "status": "success",
            "text": "grounded test answer",
            "provider_used": "test-provider",
        }

    monkeypatch.setattr(conversation_module, "gateway_ask", fake_gateway)
    result = manager.process(text)

    assert result["status"] == "success"
    assert result["intent"] == expected
    assert result["executed"] is False
    assert result["semantic_request"]["action_type"] == "none"
    assert orchestrator.calls == []
    assert len(gateway_calls) == 1
    assert "حقائق self-knowledge الموثقة" in gateway_calls[0][1]["system"]


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
    assert intent_parser.parse(text)["intent"] not in {
        Intent.AGENT_IDENTITY,
        Intent.AGENT_CAPABILITIES,
        Intent.AGENT_ARCHITECTURE,
        Intent.AGENT_EXECUTION_FLOW,
        Intent.AGENT_LIMITS,
    }
