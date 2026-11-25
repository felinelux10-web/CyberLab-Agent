"""Thirty-case controlled evaluation matrix for evidence recall and abstention."""

import pytest

from lab_v4_dev.memory.dialogue_knowledge import retrieve_dialogue_evidence


def _exchange(session_id, exchange_id, index, user, assistant, timestamp):
    return {
        "session_id": session_id,
        "exchange_id": exchange_id,
        "exchange_index": index,
        "timestamp": timestamp,
        "target": "جلسة اختبار",
        "user": user,
        "assistant": assistant,
        "response_status": "success",
    }


ART = {
    "session_id": "eval-art-session",
    "session_type": "dialogue",
    "dialogue_state": {
        "session_id": "eval-art-session",
        "transcript_archive": [
            _exchange(
                "eval-art-session", "art-1", 1,
                "أستخدم إطارًا خشبيًا قديمًا.",
                "يمكن صنفرة الإطار القديم قبل إضافة الجبس.",
                "2026-01-01T10:00:00",
            ),
            _exchange(
                "eval-art-session", "art-2", 2,
                "أصب الجبس بسماكة نحو 3 سم.",
                "يمكن استخدام طلاء أكريليك بعد جفاف الجبس.",
                "2026-01-01T10:01:00",
            ),
            _exchange(
                "eval-art-session", "art-3", 3,
                "أستخدم سكينًا ومفك براغي وملعقة في التشكيل.",
                "يمكن استعمال ورق الصنفرة لتنعيم السطح.",
                "2026-01-01T10:02:00",
            ),
            _exchange(
                "eval-art-session", "art-4", 4,
                "أضيف الألوان الذهبية والبيضاء والزرقاء بتدرجات متناسقة.",
                "يمكن تنسيق الألوان مع الخلفية الداكنة.",
                "2026-01-01T10:03:00",
            ),
            _exchange(
                "eval-art-session", "art-5", 5,
                "أستخدم الصباغة المائية.",
                "يمكنك الاستمرار بالصباغة المائية التي ذكرتها.",
                "2026-01-01T10:04:00",
            ),
            _exchange(
                "eval-art-session", "art-6", 6,
                "أضع طبقة كولا شفافة مثل الورنيش الخشبي للحماية.",
                "أقترح طبقة حماية من ورنيش الأكريليك أو شمع العسل أو شيلاك.",
                "2026-01-01T10:05:00",
            ),
        ],
    },
}

CIVILIZATIONS = {
    "session_id": "eval-civilizations-session",
    "session_type": "dialogue",
    "dialogue_state": {
        "session_id": "eval-civilizations-session",
        "transcript_archive": [
            _exchange(
                "eval-civilizations-session", "civ-1", 1,
                "ناقشنا حضارة بلاد الرافدين والمدن السومرية.",
                "تحدثنا عن الكتابة المسمارية في بلاد الرافدين.",
                "2026-02-01T10:00:00",
            ),
            _exchange(
                "eval-civilizations-session", "civ-2", 2,
                "ناقشنا مصر القديمة والأهرام.",
                "ذكرنا الأهرام والعمارة المصرية القديمة.",
                "2026-02-01T10:01:00",
            ),
        ],
    },
}

CORRECTION = {
    "session_id": "eval-correction-session",
    "session_type": "dialogue",
    "dialogue_state": {
        "session_id": "eval-correction-session",
        "transcript_archive": [
            _exchange(
                "eval-correction-session", "update-1", 1,
                "كانت سماكة الجبس ثلاثة سنتيمترات.",
                "سجلت القيمة الأولى.",
                "2026-03-01T10:00:00",
            ),
            _exchange(
                "eval-correction-session", "update-2", 2,
                "بل، التصحيح أن السماكة خمسة سنتيمترات.",
                "سجلت التصحيح إلى خمسة سنتيمترات.",
                "2026-03-02T10:00:00",
            ),
        ],
    },
}


CASES = [
    # 1–5: user-stated facts
    ("user_fact", ART, "ما سماكة الجبس؟", {"art-2"}, "user"),
    ("user_fact", ART, "ما الأدوات التي أستخدمها في التشكيل؟", {"art-3"}, "user"),
    ("user_fact", ART, "ما مادة الإطار؟", {"art-1"}, "user"),
    ("user_fact", ART, "ما الألوان التي أضيفها؟", {"art-4"}, "user"),
    ("user_fact", ART, "ما نوع الصباغة؟", {"art-5"}, "user"),
    # 6–10: assistant suggestions, kept separate from user facts
    ("assistant_suggestion", ART, "ما الذي اقترحه المساعد عن صنفرة الإطار؟", {"art-1"}, "assistant"),
    ("assistant_suggestion", ART, "ما الطلاء الذي اقترحه المساعد؟", {"art-2"}, "assistant"),
    ("assistant_suggestion", ART, "ما الذي اقترحه المساعد لتنعيم السطح؟", {"art-3"}, "assistant"),
    ("assistant_suggestion", ART, "ما طبقة الحماية التي اقترحها المساعد؟", {"art-6"}, "assistant"),
    ("assistant_suggestion", ART, "هل اقترح المساعد شمع العسل؟", {"art-6"}, "assistant"),
    # 11–15: exact-session cross-session isolation
    ("cross_session", CIVILIZATIONS, "ما الحضارة المذكورة في بلاد الرافدين؟", {"civ-1"}, "user"),
    ("cross_session", CIVILIZATIONS, "ماذا ذكرت عن مصر القديمة والأهرام؟", {"civ-2"}, "user"),
    ("cross_session", ART, "ما الأدوات التي ذكرتها في جلسة الفن؟", {"art-3"}, "user"),
    ("cross_session", ART, "ما الصباغة المائية التي ذكرتها في الفن؟", {"art-5"}, "user"),
    ("cross_session", CORRECTION, "ما السماكة التي صححتها في جلسة التحديث؟", {"update-2"}, "user"),
    # 16–20: temporal values and correction evidence
    ("temporal", CORRECTION, "ما القيمة القديمة ثلاثة سنتيمترات؟", {"update-1"}, "user"),
    ("temporal", CORRECTION, "ما القيمة الجديدة خمسة سنتيمترات؟", {"update-2"}, "user"),
    ("temporal", CORRECTION, "ما السماكة التي صححتها إلى خمسة سنتيمترات؟", {"update-2"}, "user"),
    ("temporal", CORRECTION, "هل وردت سماكة ثلاثة سنتيمترات قبل التصحيح؟", {"update-1"}, "user"),
    ("temporal", CORRECTION, "ما النص الذي ذكر التصحيح خمسة سنتيمترات؟", {"update-2"}, "user"),
    # 21–25: update and supersession questions
    ("knowledge_update", CORRECTION, "ما التصحيح الذي ذكرته؟", {"update-2"}, "user"),
    ("knowledge_update", CORRECTION, "ما السماكة بعد التعديل خمسة سنتيمترات؟", {"update-2"}, "user"),
    ("knowledge_update", CORRECTION, "هل توجد قيمة جديدة خمسة سنتيمترات؟", {"update-2"}, "user"),
    ("knowledge_update", CORRECTION, "ما العلاقة بين ثلاثة وخمسة سنتيمترات؟", {"update-1", "update-2"}, "user"),
    ("knowledge_update", CORRECTION, "هل تغيرت السماكة من ثلاثة إلى خمسة سنتيمترات؟", {"update-1", "update-2"}, "user"),
    # 26–30: unsupported details must abstain despite topical overlap
    ("abstention", ART, "كم ساعة استغرق تجفيف الجبس؟", set(), None),
    ("abstention", ART, "ما اسم ماركة الصباغة؟", set(), None),
    ("abstention", ART, "ما النسبة الدقيقة لكل لون؟", set(), None),
    ("abstention", ART, "ما درجة حرارة الغرفة أثناء التجفيف؟", set(), None),
    ("abstention", ART, "ما موديل المفك؟", set(), None),
]


@pytest.mark.parametrize(
    "category,record,query,expected_ids,expected_speaker",
    CASES,
    ids=[f"{case[0]}-{index + 1}" for index, case in enumerate(CASES)],
)
def test_dialogue_memory_eval_30_questions(
    category, record, query, expected_ids, expected_speaker,
):
    session_id = record["session_id"]
    evidence = retrieve_dialogue_evidence(
        record,
        query,
        limit=8,
        scope="saved",
        session_id=session_id,
    )
    actual_ids = {item["exchange_id"] for item in evidence}

    if category == "abstention":
        assert evidence == []
        return

    assert expected_ids <= actual_ids
    assert all(item["source_session_id"] == session_id for item in evidence)
    assert all(item["evidence_scope"] == "saved" for item in evidence)
    if expected_speaker == "user":
        assert any(item.get("matched_user_terms") for item in evidence)
    elif expected_speaker == "assistant":
        assert any(item.get("matched_assistant_terms") for item in evidence)
