from lab_v4_dev.intent.intent_parser import detect_context, parse
from lab_v4_dev.intent.intents import Intent


def _intent(text):
    result = parse(text)
    return getattr(result.intent, "value", result.intent)


def test_context_uses_whole_tokens_not_incidental_substrings():
    assert detect_context("هذا مشروعنا الصغير") == "project_level"
    assert detect_context("أتحدث عن الذاكرة في علم الحاسوب") == "device_resource"
    assert detect_context("أحب العمل الجماعي") == "general"


def test_project_word_in_discussion_does_not_trigger_project_scan():
    assert _intent("هذه مجرد كلمة مشروع في نقاش عام") == Intent.PERSONAL_CHAT


def test_bare_ram_mention_is_not_a_live_device_query():
    assert _intent("RAM") == Intent.PERSONAL_CHAT


def test_explicit_phone_ram_measurement_is_not_confused_with_explanation():
    assert _intent("كم RAM متاح في هاتفي؟") == Intent.UNSUPPORTED


def test_explicit_phone_storage_query_remains_routable():
    assert _intent("مساحة الهاتف") == Intent.SPACE
