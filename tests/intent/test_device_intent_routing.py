from types import SimpleNamespace

import pytest

from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent

CLEANUP_INTENTS = {Intent.CLEAN, Intent.CLEAN_DEVICE, Intent.CLEANUP_CODE}


@pytest.fixture(autouse=True)
def isolate_parser_fallbacks(monkeypatch):
    """Keep parser tests deterministic and prevent disk/network side effects."""
    from lab_v4_dev.intent import intent_cache, llm_intent_resolver
    from lab_v4_dev.nlu import context_resolver

    monkeypatch.setattr(intent_cache, "get", lambda _text: None)
    monkeypatch.setattr(intent_cache, "save", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(llm_intent_resolver, "save", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(llm_intent_resolver, "resolve", lambda _text: Intent.UNCLEAR)
    monkeypatch.setattr(context_resolver, "save_state", lambda *_args, **_kwargs: None)


def intent_for(text):
    return parse(text).get("intent")


@pytest.mark.parametrize(
    "text",
    [
        "الهاتف",
        "هاتف",
        "هاتفي",
        "الجهاز",
        "جهاز",
        "جهازي",
        "جوال",
        "الجوال",
        "جوالي",
        "هاتفي لا يعمل",
        "ما حالة هاتفي؟",
        "لدي مشروع على الهاتف",
        "لدي ملف في الهاتف",
        "اشرح لي شيئاً عن الهاتف",
        "أريد أن نتحدث عن الهاتف",
        "الجهاز بطيء",
        "ما رأيك في هذا الجهاز؟",
        "مساحة الهاتف",
        "حلل الهاتف",
        "اشرح الهاتف",
        "افحص الهاتف",
    ],
)
def test_device_topic_mentions_do_not_create_cleanup_intents(text):
    assert intent_for(text) not in CLEANUP_INTENTS


def test_ram_and_memory_are_not_storage_family_aliases():
    from lab_v4_dev.intent.fuzzy_normalizer import deep_normalize
    from lab_v4_dev.intent.keyword_families import match_family

    assert deep_normalize("الرام") == "رام"
    assert match_family(deep_normalize("الرام")) is None
    assert match_family(deep_normalize("ذاكرة الجهاز")) is None


@pytest.mark.parametrize(
    "text",
    ["مساحة الهاتف", "مساحة الجهاز", "كم المساحة المتبقية", "كم مساحة التخزين؟"],
)
def test_storage_queries_remain_space(text):
    assert intent_for(text) == Intent.SPACE


@pytest.mark.parametrize(
    "text",
    [
        "الرام",
        "كم الرام",
        "كم RAM عندي؟",
        "ذاكرة الهاتف",
        "ذاكرة الجهاز",
        "كم الذاكرة؟",
    ],
)
def test_live_device_memory_queries_are_explicitly_unsupported_without_llm(
    text, monkeypatch
):
    from lab_v4_dev.intent import llm_intent_resolver

    def unexpected_llm_call(_text):
        pytest.fail("device-memory status must not reach the LLM intent fallback")

    monkeypatch.setattr(llm_intent_resolver, "resolve", unexpected_llm_call)
    result = parse(text)

    assert result.get("intent") == Intent.UNSUPPORTED
    assert result.get("semantic_pattern") == "DEVICE_MEMORY_UNSUPPORTED"
    assert result.get("intent") not in {
        Intent.SPACE,
        Intent.SYSTEM_STATUS,
        Intent.MEMORY_STATUS,
    }


def test_device_memory_query_cannot_be_hijacked_by_stale_system_status_cache(monkeypatch):
    from lab_v4_dev.intent import intent_cache, llm_intent_resolver

    monkeypatch.setattr(intent_cache, "get", lambda _text: Intent.SYSTEM_STATUS)
    monkeypatch.setattr(
        llm_intent_resolver,
        "resolve",
        lambda _text: pytest.fail("memory status must resolve before the LLM fallback"),
    )

    result = parse("ذاكرة الجهاز")

    assert result.get("intent") == Intent.UNSUPPORTED
    assert result.get("semantic_pattern") == "DEVICE_MEMORY_UNSUPPORTED"


@pytest.mark.parametrize(
    "text",
    [
        "ما هي ذاكرة الهاتف؟",
        "اشرح لي RAM في الهاتف",
        "ما الفرق بين RAM والتخزين؟",
    ],
)
def test_memory_knowledge_questions_stay_on_general_explanation_path(text):
    result = parse(text)

    assert result.get("intent") == Intent.PERSONAL_CHAT
    assert result.get("intent") not in {Intent.SPACE, Intent.UNSUPPORTED, Intent.SYSTEM_STATUS}


def test_device_memory_unsupported_result_does_not_reach_chat_or_orchestrator(monkeypatch):
    class NeverOrchestrator:
        def handle(self, *_args, **_kwargs):
            pytest.fail("unsupported device-memory query must not reach execution")

    manager = ConversationManager(NeverOrchestrator())
    monkeypatch.setattr(
        manager,
        "_handle_chat",
        lambda *_args, **_kwargs: pytest.fail("unsupported query must not reach chat LLM"),
    )

    result = manager.process("ذاكرة الجهاز")

    assert result["status"] == "unsupported"
    assert result["intent"] == Intent.UNSUPPORTED
    assert "RAM" in result["text"]
    assert result["executed"] is False


def test_how_are_you_is_social_not_agent_status():
    result = parse("كيف الحال")

    assert result.get("intent") == Intent.PERSONAL_CHAT
    assert result.get("conversation_act") == "ASSISTANT_STATE_QUERY"


@pytest.mark.parametrize(
    "text",
    [
        "نظف الهاتف",
        "تنظيف الهاتف",
        "نظف جهازي",
        "تنظيف الجهاز",
        "تنظيف مساحة الهاتف",
        "نظف مساحة الهاتف",
    ],
)
def test_cleanup_action_and_device_target_resolve_to_clean_device(text):
    assert intent_for(text) == Intent.CLEAN_DEVICE


@pytest.mark.parametrize("text", ["نظف الكود", "نظف المشروع", "نظف المشروع على الهاتف"])
def test_explicit_code_target_outweighs_device_topic(text):
    assert intent_for(text) == Intent.CLEANUP_CODE


@pytest.mark.parametrize("text", ["نظف", "تنظيف", "أريد تنظيف", "نظف المساحة"])
def test_cleanup_action_without_resolved_target_remains_generic_clean(text):
    assert intent_for(text) == Intent.CLEAN


@pytest.mark.parametrize("text", ["لا تنظف الهاتف", "لا أريد تنظيف الهاتف", "لن تنظف جهازي"])
def test_negated_cleanup_request_is_not_executable(text):
    assert intent_for(text) not in CLEANUP_INTENTS


def test_generic_clean_requests_clarification_without_running_cleaner(monkeypatch):
    from lab_v4_dev.core import cleaner

    calls = []
    monkeypatch.setattr(cleaner, "run_full_clean", lambda: calls.append("called"))
    orchestrator = Orchestrator(SimpleNamespace(runtime=None))

    result = orchestrator._route(Intent.CLEAN, "", "general", "نظف")

    assert result["status"] == "needs_clarification"
    assert "ما الذي تريد تنظيفه" in result["text"]
    assert calls == []


def test_explicit_device_route_calls_only_mocked_cleaner(monkeypatch):
    from lab_v4_dev.core import cleaner

    calls = []
    monkeypatch.setattr(
        cleaner,
        "run_full_clean",
        lambda: calls.append("called")
        or {
            "before_mb": 100,
            "after_mb": 101,
            "freed_mb": 1,
            "freed_kb": 1024,
            "details": [],
        },
    )
    orchestrator = Orchestrator(SimpleNamespace(runtime=None))

    result = orchestrator._route(
        Intent.CLEAN_DEVICE, "", "general", "نظف الهاتف"
    )

    assert result["status"] == "success"
    assert result["intent"] == Intent.CLEAN_DEVICE
    assert calls == ["called"]
