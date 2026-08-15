import pytest

from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent


def intent_for(text):
    p = parse(text)
    return p.get("intent")


def test_generic_clean_is_ambiguous():
    inputs = ["تنظيف", "نظف", "نظّف", "أريد تنظيف"]
    for t in inputs:
        intent = intent_for(t)
        assert intent != Intent.CLEAN_DEVICE, f"Generic '{t}' should not be CLEAN_DEVICE"
        assert intent == "unsupported", f"Generic '{t}' should be ambiguous/unsupported, got {intent}"


def test_explicit_device_maps_to_clean_device():
    inputs = ["نظف الهاتف", "نظّف الهاتف", "تنظيف الهاتف", "نظف جهازي", "تنظيف الجهاز", "نظف المساحة"]
    for t in inputs:
        intent = intent_for(t)
        assert intent == Intent.CLEAN_DEVICE, f"Device-target '{t}' must map to CLEAN_DEVICE, got {intent}"


def test_explicit_code_maps_to_cleanup_code():
    inputs = ["نظف الكود", "تنظيف الكود", "نظف المشروع"]
    for t in inputs:
        intent = intent_for(t)
        assert intent == Intent.CLEANUP_CODE, f"Code-target '{t}' must map to CLEANUP_CODE, got {intent}"


def test_substring_does_not_trigger_device_clean():
    # words where 'نظف' appears as substring should not trigger device cleaning
    inputs = ["تعليماتتنظيف", "تنظيفي", "مشكلةتنظيفالهاتف"]
    for t in inputs:
        intent = intent_for(t)
        assert intent != Intent.CLEAN_DEVICE, f"Substring case '{t}' must not trigger CLEAN_DEVICE, got {intent}"


def test_delete_behavior_preserved():
    intent = intent_for("احذف الملف")
    assert intent == Intent.DELETE_FILE, f"Delete phrase must map to DELETE_FILE, got {intent}"
