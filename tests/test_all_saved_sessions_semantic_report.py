from types import SimpleNamespace

from lab_v4_dev.memory import session_state


def _dialogue(session_id, title, user_text, assistant_text, target):
    return {
        "session_id": session_id,
        "session_type": "dialogue",
        "title": title,
        "status": "completed",
        "dialogue_state": {
            "session_id": session_id,
            "last_topic": target,
            "exchange_archive": [{
                "session_id": session_id,
                "user": user_text,
                "assistant": assistant_text,
                "target": target,
                "context_kind": "dialogue",
                "conversation_domain": "general",
            }],
        },
    }


def test_detailed_report_for_all_sessions_is_classified_as_saved_collection():
    selected = session_state.session_selector(
        "اكتب تقرير مفصل لهذه الجليات كلها"
    )
    assert selected == {"kind": "list", "report_mode": "full"}

    corrected_followup = session_state.session_selector(
        "لا تعرض محتوى الجلسات بل قلت لك اكتب تقرير مفصل"
    )
    assert corrected_followup == {"kind": "list", "report_mode": "full"}


def test_all_sessions_report_is_aggregate_semantic_and_never_a_transcript(monkeypatch):
    art = _dialogue(
        "saved-art-01",
        "الفن التجريدي والنقش البارز",
        "ما الفرق بين الفن التجريدي والنقش البارز؟",
        "يرتبط الفرق بأسلوب معالجة الشكل والسطح. الفن التجريدي لا يلتزم بتمثيل الواقع، بينما يجعل النقش البارز العناصر تبرز من الخلفية.",
        "الفن التجريدي والنقش البارز",
    )
    astronomy = _dialogue(
        "saved-space-02",
        "النجوم النابضة",
        "كيف تعمل النجوم النابضة؟",
        "تنتج النجوم النابضة إشارات دورية بسبب دوران نجم نيوتروني وإصدار حزم إشعاعية.",
        "النجوم النابضة",
    )
    work = {
        "session_id": "saved-work-03",
        "session_type": "work",
        "title": "إصلاح اختبارات المشروع",
        "active_goal": "إصلاح اختبارات المشروع",
        "status": "paused",
        "completed_work": [{"label": "إصلاح اختبار التوجيه", "status": "success", "verified": True}],
        "pending_tasks": ["تشغيل مجموعة اختبارات الاستمرارية"],
        "next_step": "تشغيل مجموعة اختبارات الاستمرارية",
    }
    records = {
        item["session_id"]: item for item in (art, astronomy, work)
    }
    index = [art, astronomy, work]
    monkeypatch.setattr(session_state, "get_session_index", lambda: index)
    monkeypatch.setattr(session_state, "get_session_by_id", lambda session_id: records.get(session_id, {}))

    report = session_state.build_all_sessions_report(index)

    assert "التقرير التحليلي لجميع الجلسات المحفوظة" in report
    assert "إجمالي الجلسات المشمولة: 3" in report
    assert "جلسات الحوار: 2" in report
    assert "جلسات العمل: 1" in report
    assert "الفن التجريدي والنقش البارز" in report
    assert "النجوم النابضة" in report
    assert "إصلاح اختبارات المشروع" in report
    assert "تشغيل مجموعة اختبارات الاستمرارية" in report
    assert "ما الفرق بين الفن التجريدي والنقش البارز؟" not in report
    assert "كيف تعمل النجوم النابضة؟" not in report
    assert "يرتبط الفرق بأسلوب معالجة الشكل والسطح. الفن التجريدي لا يلتزم" not in report
    assert "=== نص الحوار المحفوظ حرفيًا ===" not in report


def test_report_does_not_treat_provider_failure_as_session_knowledge():
    exchange = {
        "user": "كيف تشتغل أنت كوكيل؟",
        "assistant": (
            "آخر نقطة محفوظة في هذا الفرع: أنا بخير. "
            "تعذر توليد شرح جديد لأن المزود غير متاح في هذه المحاولة."
        ),
        "target": "آخر نقطة محفوظة في هذا الفرع",
    }
    insights = session_state._dialogue_exchange_insights(exchange)
    assert insights
    assert not any("أنا بخير" in item for item in insights)
    assert not any("تعذر توليد شرح" in item for item in insights)
    assert any("هوية الوكيل وآلية عمله" in item for item in insights)
