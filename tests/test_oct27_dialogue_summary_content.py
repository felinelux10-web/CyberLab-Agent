from lab_v4_dev.memory.session_state import build_session_restore_summary


def test_standard_dialogue_summary_uses_saved_user_assistant_content():
    summary = build_session_restore_summary(
        {
            "session_id": "dialogue-content-1",
            "session_type": "dialogue",
            "updated_at": "2026-10-27T08:00:00",
            "active_goal": "حفظ سياق الحوار",
            "dialogue_state": {
                "session_id": "dialogue-content-1",
                "last_topic": "حفظ سياق الحوار",
                "exchange_archive": [
                    {
                        "session_id": "dialogue-content-1",
                        "user": "تحدثنا عن أثر الذكاء الاصطناعي في التعليم",
                        "assistant": "ناقشنا فوائد التخصيص ومخاطر الاعتماد الزائد",
                        "target": "",
                    },
                    {
                        "session_id": "dialogue-content-1",
                        "user": "ثم انتقلنا إلى كيفية حماية الخصوصية",
                        "assistant": "توقفنا عند تقليل جمع البيانات وشرح الموافقة بوضوح",
                        "target": "الخصوصية",
                    },
                ],
            },
        }
    )

    assert "ما نوقش فعليًا في الحوار" in summary
    assert "أثر الذكاء الاصطناعي في التعليم" in summary
    assert "فوائد التخصيص ومخاطر الاعتماد الزائد" in summary
    assert "تقليل جمع البيانات" in summary
    assert "المستخدم: تحدثنا عن أثر الذكاء الاصطناعي" not in summary
    assert "الوكيل: ناقشنا فوائد التخصيص" not in summary


def test_transcript_mode_remains_literal_and_separate():
    summary = build_session_restore_summary(
        {
            "session_id": "dialogue-content-2",
            "session_type": "dialogue",
            "dialogue_state": {
                "session_id": "dialogue-content-2",
                "exchange_archive": [
                    {
                        "session_id": "dialogue-content-2",
                        "user": "ما نقطة التوقف؟",
                        "assistant": "توقفنا عند المثال الثاني.",
                    }
                ],
            },
        },
        report_mode="transcript",
    )

    assert "=== نص الحوار المحفوظ حرفيًا ===" in summary
    assert "[1] المستخدم:" in summary
    assert "[1] الوكيل:" in summary
    assert "ما نوقش فعليًا في الحوار" not in summary
