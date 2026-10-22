from lab_v4_dev.memory.session_state import session_selector


def test_all_saved_session_summary_requests_select_list_mode():
    prompts = (
        "اعرض جميع الجلسات المحفوظة",
        "اعرض ملخصات جميع الجلسات",
        "أعطني ملخصات كل الجلسات",
        "أريد قائمة الجلسات المحفوظة",
        "جميع الملخصات",
    )
    for prompt in prompts:
        assert session_selector(prompt)["kind"] == "list", prompt


def test_specific_session_number_keeps_number_selection():
    selected = session_selector("اعرض ملخص الجلسة رقم 3")
    assert selected["kind"] == "number"
    assert selected["number"] == 3


def test_latest_session_request_does_not_become_list_request():
    assert session_selector("استرجع آخر جلسة")["kind"] == "latest"
