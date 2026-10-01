from types import SimpleNamespace

import pytest

from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent


CLEANUP_INTENTS = {Intent.CLEAN, Intent.CLEAN_DEVICE, Intent.CLEANUP_CODE}


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


@pytest.mark.parametrize(
    "text",
    [
        "نظف الهاتف",
        "تنظيف الهاتف",
        "نظف جهازي",
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
