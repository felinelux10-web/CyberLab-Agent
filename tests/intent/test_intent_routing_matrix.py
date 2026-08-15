import pytest
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent

@pytest.mark.parametrize("text,expected", [
    ("تنظيف", "unsupported"),
    ("نظف", "unsupported"),
    ("نظف الهاتف", Intent.CLEAN_DEVICE),
    ("تنظيف الجهاز", Intent.CLEAN_DEVICE),
    ("نظف المساحة", Intent.CLEAN_DEVICE),
    ("نظف الكود", Intent.CLEANUP_CODE),
    ("نظف المشروع", Intent.CLEANUP_CODE),
    ("احذف الملف test.py", Intent.DELETE_FILE),
    ("اقرأ الملف test.py", Intent.READ_FILE),
    ("حلل الملف test.py", Intent.ANALYZE_CODE),
    ("قارن بين الإصدارين", Intent.COMPARE_VERSIONS),
    ("ما حالة النظام", Intent.STATUS),
    ("هل النظام سليم", Intent.HEALTH),
    ("حلل المشروع", Intent.PROJECT_SCAN),
    ("اشرح كيف يعمل النظام", Intent.CYBER_EXPLAIN),
])
def test_intent_routing_matrix(text, expected):
    result = parse(text)
    intent = result.get("intent")
    assert intent == expected
