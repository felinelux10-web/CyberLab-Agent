from lab_v4_dev.memory import session_state


def test_all_session_summary_requests_use_saved_session_summary_route():
    requests = [
        "اكتب ملخص لكل جلسة",
        "اكتب تقرير ملخص لكل جلسة",
        "اكتب ملخص لكل الجلسات المحفوظة",
        "اكتب ملهص لجنيع الجلسات المحفوظة عندك يعني كل جلسة تمتب رقمها وملهص تحتها",
        "اكتب قائمة فيها جميع الجلسات المحفوظة ثم اكتب عنوان وملخص صغير لكل جلسة",
        "اكتب ملخص للجلسات المحفوظة كلها",
    ]

    for request in requests:
        selected = session_state.session_selector(request)
        assert selected == {"kind": "list", "report_mode": "summaries"}, (
            request,
            selected,
        )


def test_summary_of_this_ambiguous_session_is_not_mapped_to_latest():
    selected = session_state.session_selector(
        "اكتب ملخص هذه الجلسة التي عرضتها أنت"
    )
    assert selected == {"kind": "reference", "report_mode": "standard"}


def test_listing_all_sessions_without_summary_stays_a_plain_list():
    selected = session_state.session_selector("اعرض جميع الجلسات المحفوظة")
    assert selected["kind"] == "list"
    assert selected["report_mode"] == "standard"


def test_dialogue_brief_summary_uses_only_completed_exchanges_from_that_session():
    saved = {
        "session_id": "art-session",
        "session_type": "dialogue",
        "title": "حفظ سياق الحوار",
        "dialogue_state": {
            "session_id": "art-session",
            "last_topic": "الفن التجريدي والنحت البارز",
            "exchange_archive": [
                {
                    "session_id": "art-session",
                    "user": "ناقشنا الفن التجريدي والنحت البارز وعلاقتهما بالفراغ.",
                    "assistant": "تطرقنا إلى التكوين والكتلة والعلاقة بين الشكل والفراغ.",
                    "target": "الفن التجريدي والنحت البارز",
                },
                {
                    "session_id": "unrelated-work",
                    "user": "شرح SQL injection واختبارات المشروع.",
                    "assistant": "هذا تبادل من جلسة أخرى ولا ينبغي دمجه.",
                    "target": "SQL injection",
                },
                {
                    "session_id": "art-session",
                    "user": "حفظ سياق الحوار",
                    "assistant": "تم حفظ السياق.",
                    "target": "حفظ سياق الحوار",
                },
            ],
        },
    }

    brief = session_state.build_session_brief_summary(saved)

    assert brief["session_id"] == "art-session"
    assert "الفن التجريدي والنحت البارز" in brief["topic"]
    assert "الفن التجريدي" in brief["summary"]
    assert "SQL injection" not in brief["summary"]
    assert "حفظ سياق الحوار" not in brief["summary"]


def test_work_brief_summary_uses_goal_evidence_and_next_step():
    saved = {
        "session_id": "work-session",
        "session_type": "work",
        "title": "كتابة سكريبت يعرض معلومات النظام",
        "active_goal": "كتابة سكريبت يعرض معلومات النظام",
        "completed_work": ["إنشاء السكريبت الأساسي"],
        "next_step": "تشغيل الاختبارات",
        "context_state": {"subject": "كتابة سكريبت يعرض معلومات النظام"},
    }

    brief = session_state.build_session_brief_summary(saved)

    assert "كتابة سكريبت" in brief["topic"]
    assert "إنشاء السكريبت الأساسي" in brief["summary"]
    assert "تشغيل الاختبارات" in brief["summary"]


def test_saved_session_choice_is_resolved_by_option_or_distinctive_topic():
    candidates = [
        {
            "session_id": "art-session-a",
            "title": "حوار: الفن والرسم والنحت والنقش",
            "topic": "الفن والرسم والنحت والنقش",
            "summary": "مضمون الحوار: ناقشنا الفن التجريدي والنحت البارز وعلاقتهما بالفراغ.",
        },
        {
            "session_id": "art-session-b",
            "title": "حوار: الفن والرسم والنحت والنقش",
            "topic": "الفن والرسم والنحت والنقش",
            "summary": "مضمون الحوار: ناقشنا الرسم التاريخي وأدوات النقش التقليدي.",
        },
    ]

    assert session_state.resolve_saved_session_choice("2", candidates) == "art-session-b"
    assert (
        session_state.resolve_saved_session_choice(
            "الجلسة التي كنا نتحدث فيها عن الفن التجريدي والنحت البارز",
            candidates,
        )
        == "art-session-a"
    )
    assert (
        session_state.resolve_saved_session_choice(
            "اكتب ملخص هذه الجلسة التي عرضتها أنت",
            candidates,
        )
        is None
    )
