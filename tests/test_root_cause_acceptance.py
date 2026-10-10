import ast
from pathlib import Path
from types import SimpleNamespace

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent


def test_work_resume_is_not_unclear_or_unsupported():
    assert parse("استكمال العمل")["intent"] == Intent.RESUME
    assert parse("استكمال الجلسة")["intent"] == Intent.SESSION_RESTORE


def test_resume_requires_actionable_checkpoint(tmp_path, monkeypatch):
    import lab_v4_dev.memory.session_state as session_state
    import lab_v4_dev.core.orchestrator as orchestrator_module

    checkpoint = {
        "active_goal": "إضافة ميزة إلى اللعبة",
        "next_step": "استكمال تعديل اللعبة",
        "last_files": ["game.py"],
        "project_root": str(tmp_path),
        "context_state": {"last_intent": "modify_code", "current_file": "game.py"},
    }
    (tmp_path / "game.py").write_text("print('game')\n", encoding="utf-8")
    monkeypatch.setattr(session_state, "load_session", lambda: checkpoint)
    restored = []
    agent = SimpleNamespace(
        restore_session_context=lambda: restored.append(True) or True,
        _meta=SimpleNamespace(get_version=lambda: "test"),
    )
    result = Orchestrator(agent).handle(
        "استكمال العمل",
        parsed={"intent": Intent.RESUME, "target": "", "raw": "استكمال العمل"},
    )
    assert result["status"] == "success"
    assert result["next_step"] == "استكمال تعديل اللعبة"
    assert result["file"].endswith("game.py")
    assert restored == [True]


def test_resume_rejects_dialogue_only_checkpoint(monkeypatch):
    import lab_v4_dev.memory.session_state as session_state

    monkeypatch.setattr(
        session_state,
        "load_session",
        lambda: {
            "active_goal": "حفظ الجلسة",
            "next_step": "استكمال: حفظ الجلسة",
            "last_files": [],
            "context_state": {"last_intent": "cyber_explain", "subject": "SQL Injection"},
        },
    )
    agent = SimpleNamespace(restore_session_context=lambda: True)
    result = Orchestrator(agent).handle(
        "استكمال العمل",
        parsed={"intent": Intent.RESUME, "target": "", "raw": "استكمال العمل"},
    )
    assert result["status"] == "needs_clarification"
    assert "قابلة للاستئناف" in result["text"]


def test_new_session_does_not_generate_code_or_reuse_old_file(tmp_path):
    class FakeOrchestrator:
        def __init__(self):
            self.context = ContextStore()
            self.context.current_file = str(tmp_path / "old.py")
            self.agent = SimpleNamespace()
            self.calls = 0

        def handle(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("new session must not dispatch to execution or chat")

        def reset_conversation_context(self):
            self.context.current_file = None

    orchestrator = FakeOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))
    result = manager.process("جلسة جديدة")
    assert result["status"] == "success"
    assert result["intent"] == Intent.RESTART
    assert "لم يتم إنشاء" in result["text"]
    assert orchestrator.context.current_file is None
    assert orchestrator.calls == 0


def test_dialogue_recall_keeps_user_and_assistant_pairs_and_excludes_work():
    context = ContextStore()
    memory = DialogueMemory(context)
    memory.state.exchange_archive = [
        {
            "user": "اشرح SQL Injection",
            "assistant": "توقفنا عند آلية الحدوث.",
            "target": "SQL Injection",
            "context_kind": "dialogue",
            "conversation_domain": "technical",
        },
        {
            "user": "عدّل game.py",
            "assistant": "تم تعديل الملف.",
            "target": "game.py",
            "context_kind": "work",
            "conversation_domain": "execution",
        },
        {
            "user": "اشرح CSRF",
            "assistant": "توقفنا عند آلية الحماية.",
            "target": "CSRF",
            "context_kind": "dialogue",
            "conversation_domain": "technical",
        },
    ]
    manager = ConversationManager(SimpleNamespace(context=context), memory)
    result = manager._conversation_history_answer(
        "ماذا كنا نقول؟",
        {"conversation_act": "CONVERSATION_HISTORY_QUERY"},
    )
    assert result["status"] == "success"
    assert "المستخدم: اشرح SQL Injection" in result["text"]
    assert "الوكيل: توقفنا عند آلية الحدوث." in result["text"]
    assert "المستخدم: اشرح CSRF" in result["text"]
    assert "game.py" not in result["text"]


def test_session_restore_returns_structured_semantic_summary(monkeypatch):
    import lab_v4_dev.memory.session_state as session_state

    checkpoint = {
        "session_id": "session-summary-1",
        "timestamp": "2026-10-10T14:00:00",
        "active_goal": "إكمال منظومة الاستمرارية",
        "completed_work": ["إصلاح توجيه النوايا", "حفظ تبادلات الحوار"],
        "next_step": "اختبار الاستعادة بعد إعادة التشغيل",
        "last_files": ["game.py", "conversation_manager.py"],
        "decisions": ["عدم تنفيذ الخطوة التالية تلقائيًا"],
        "open_questions": ["هل نحتاج اختبارًا إضافيًا؟"],
        "context_state": {"last_intent": "modify_code"},
        "dialogue_state": {
            "last_topic": "استمرارية الجلسات",
            "exchange_archive": [
                {"user": "ماذا أصلحنا؟", "assistant": "أصلحنا دورة الاستمرارية."},
                {"user": "أين توقفنا؟", "assistant": "عند اختبار الاستعادة."},
            ],
        },
    }
    monkeypatch.setattr(session_state, "load_session", lambda: checkpoint)
    agent = SimpleNamespace(restore_session_context=lambda: True)
    result = Orchestrator(agent).handle(
        "استكمل الجلسة",
        parsed={"intent": Intent.SESSION_RESTORE, "target": "", "context": "general"},
    )
    text = result["text"]
    assert result["status"] == "success"
    for section in (
        "التقرير الدلالي للجلسة", "الموضوع والهدف", "ما نوقش فعليًا",
        "ما نُفّذ والإنجازات المؤكدة", "الحالة الحالية ونقطة التوقف",
        "الملفات والقرارات والقيود المهمة",
    ):
        assert section in text
    assert "إصلاح توجيه النوايا" in text
    assert "اختبار الاستعادة بعد إعادة التشغيل" in text
    assert "المستخدم: ماذا أصلحنا؟" not in text
    assert "الوكيل: أصلحنا دورة الاستمرارية." not in text
    assert "لم يتم تنفيذ الخطوة التالية تلقائيًا" in text


def test_session_summary_does_not_fallback_to_legacy_transcript():
    from lab_v4_dev.memory.session_state import build_session_restore_summary

    summary = build_session_restore_summary({
        "active_goal": "حوار محفوظ",
        "next_step": "متابعة الحوار",
        "dialogue_state": {
            "history": [
                {"role": "user", "content": "اشرح الفكرة"},
                {"role": "assistant", "content": "توقفنا عند المثال"},
            ],
        },
    })
    assert "المستخدم: اشرح الفكرة" not in summary
    assert "الوكيل: توقفنا عند المثال" not in summary
    assert "غير محدد من البيانات المتاحة" in summary


def test_session_index_keeps_twenty_sessions_and_restores_old_details(monkeypatch, tmp_path):
    import lab_v4_dev.memory.session_state as session_state

    archive = tmp_path / "session_archive.json"
    details = tmp_path / "sessions"
    monkeypatch.setattr(session_state, "_archive_file", lambda: str(archive))
    monkeypatch.setattr(session_state, "_details_dir", lambda: str(details))
    monkeypatch.setattr(session_state, "_session_file", lambda: str(tmp_path / "session_state.json"))

    saved = []
    for index in range(25):
        item = session_state.save_session(
            active_goal=f"موضوع الجلسة {index}",
            completed=[f"إنجاز {index}"],
            next_step=f"خطوة {index}",
            title=f"جلسة موضوع {index}",
            project="CyberLab Agent" if index == 3 else "Other Project",
            dialogue_state={"exchange_archive": [{"user": f"سؤال {index}", "assistant": f"جواب {index}"}]},
        )
        saved.append(item)

    assert len(session_state.get_session_index()) == 25
    matches = session_state.search_sessions("موضوع الجلسة 3")
    assert matches and matches[0]["session_id"] == saved[3]["session_id"]
    restored = session_state.get_session_by_id(saved[3]["session_id"])
    assert restored["active_goal"] == "موضوع الجلسة 3"
    assert restored["dialogue_state"]["exchange_archive"][0]["assistant"] == "جواب 3"


def test_natural_project_session_return_reaches_session_selector():
    class CapturingOrchestrator:
        def __init__(self):
            self.context = ContextStore()
            self.calls = []

        def handle(self, *args, **kwargs):
            self.calls.append(kwargs)
            return {"status": "success", "intent": Intent.SESSION_RESTORE, "text": "تم الاختبار"}

    orchestrator = CapturingOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))
    result = manager.process("أريد العودة إلى جلسة مشروع CyberLab Agent")
    assert result["status"] == "success"
    assert orchestrator.calls[-1]["parsed"]["intent"] == Intent.SESSION_RESTORE
    assert orchestrator.calls[-1]["parsed"]["session_selector"]["kind"] == "search"


def test_session_analyzer_derives_grounded_fields_without_transcript_leak():
    from lab_v4_dev.memory.session_state import analyze_session, build_session_restore_summary

    session = {
        "session_id": "semantic-1",
        "active_goal": "إصلاح استعادة الجلسات",
        "status": "paused",
        "next_step": "تشغيل اختبار الاستعادة",
        "completed_work": ["تحديد سبب فقد السياق"],
        "last_files": ["session_state.py"],
        "dialogue_state": {
            "last_topic": "استعادة الجلسات",
            "exchange_archive": [{"user": "معلومة خاصة لا يجب عرضها", "assistant": "رد خاص"}],
        },
    }
    report = analyze_session(session)
    assert report["topic"] == "استعادة الجلسات"
    assert report["active_goal"] == "إصلاح استعادة الجلسات"
    assert report["completed_work"] == ["تحديد سبب فقد السياق"]
    assert report["confirmed_achievements"] == []
    assert report["pending_tasks"] == ["تشغيل اختبار الاستعادة"]
    rendered = build_session_restore_summary(session)
    assert "معلومة خاصة لا يجب عرضها" not in rendered
    assert "رد خاص" not in rendered
    assert "تشغيل اختبار الاستعادة" in rendered


def test_session_report_commands_extract_clean_query_and_report_mode():
    from lab_v4_dev.memory.session_state import session_selector

    request = session_selector(
        "ابحث في الجلسات المحفوظة عن جلسة SQL Injection، واعرض معرّف الجلسة وموضوعها وحالتها فقط"
    )
    assert request == {"kind": "search", "query": "SQL Injection", "report_mode": "compact"}
    assert session_selector("استعد جلسة بمعرّف semantic-1")["kind"] == "id"


def test_long_multi_topic_session_extracts_structured_content_not_transcript():
    from lab_v4_dev.memory.session_state import analyze_session, build_session_restore_summary

    session = {
        "session_id": "long-1", "active_goal": "إكمال إصلاح الاستعادة", "status": "paused",
        "next_step": "تشغيل الاختبارات النهائية", "decisions": ["عدم التنفيذ التلقائي"],
        "completed_work": ["إصلاح محلل النوايا", "اقترح إضافة تحسين لاحق"],
        "execution_results": [{"status": "success", "action": "write_file"}],
        "test_results": [{"status": "passed", "label": "اختبارات الاستمرارية"}],
        "dialogue_state": {"last_topic": "استعادة الجلسات", "exchange_archive": [
            {"target": "تحليل النوايا", "user": "رسالة سرية 1"},
            {"target": "فهرسة الجلسات", "user": "رسالة سرية 2"},
            {"target": "استعادة الجلسات", "user": "رسالة سرية 3"},
        ]},
    }
    report = analyze_session(session)
    assert {"تحليل النوايا", "فهرسة الجلسات", "استعادة الجلسات"} <= set(report["topics"])
    assert "write_file" in report["confirmed_achievements"]
    assert "اختبارات الاستمرارية" in report["confirmed_achievements"]
    assert "اقترح إضافة تحسين لاحق" not in report["confirmed_achievements"]
    rendered = build_session_restore_summary(session)
    assert "رسالة سرية 1" not in rendered and "رسالة سرية 2" not in rendered


def test_checkpoint_rebuilds_summary_and_changes_completed_to_paused(monkeypatch, tmp_path):
    import lab_v4_dev.memory.session_state as session_state

    monkeypatch.setattr(session_state, "_session_file", lambda: str(tmp_path / "session.json"))
    monkeypatch.setattr(session_state, "_archive_file", lambda: str(tmp_path / "archive.json"))
    monkeypatch.setattr(session_state, "_details_dir", lambda: str(tmp_path / "details"))
    monkeypatch.setattr(session_state, "_write_session_detail", lambda _data: None)
    monkeypatch.setattr("lab_v4_dev.awareness.project_knowledge.save_session", lambda _data: None)
    first = session_state.save_session(
        active_goal="مهمة مكتملة", completed=["تم التنفيذ"], status="completed",
        dialogue_state={"last_topic": "الموضوع الأول"}, summary="ملخص قديم يجب ألا يبقى",
    )
    assert "ملخص قديم" not in first["summary"]
    monkeypatch.setattr(session_state, "load_session", lambda: first)
    updated = session_state.save_recoverable_checkpoint(
        active_goal="مهمة مستأنفة", next_step="متابعة الاختبار",
        context_state={"last_intent": "run_tests"},
    )
    assert updated["status"] == "paused"
    assert "متابعة الاختبار" in updated["summary"]
    assert "مهمة مستأنفة" in updated["summary"]


def test_failed_result_is_not_reported_as_success_and_sessions_do_not_mix():
    from lab_v4_dev.memory.session_state import analyze_session, build_session_restore_summary

    failed = {"session_id": "failed-1", "active_goal": "مهمة أ", "status": "failed",
              "context_state": {"last_result": {"status": "failed", "action": "run_tests"}},
              "dialogue_state": {"exchange_archive": [{"target": "موضوع أ", "user": "سر أ"}]}}
    other = {"session_id": "other-1", "active_goal": "مهمة ب", "status": "completed",
             "execution_results": [{"status": "success", "label": "نتيجة ب"}],
             "dialogue_state": {"exchange_archive": [{"target": "موضوع ب", "user": "سر ب"}]}}
    assert analyze_session(failed)["status"] == "failed"
    assert not analyze_session(failed)["confirmed_achievements"]
    assert analyze_session(other)["topic"] == "موضوع ب"
    assert "موضوع أ" not in build_session_restore_summary(other)
    assert "سر أ" not in build_session_restore_summary(failed)
    assert "سر ب" not in build_session_restore_summary(other)


def test_unverified_descriptions_never_become_confirmed_achievements():
    from lab_v4_dev.memory.session_state import analyze_session

    session = {
        "session_id": "evidence-1",
        "completed_work": ["إضافة نظام النسخ الاحتياطي", "تصميم خطة التحقق القادمة"],
        "confirmed_achievements": ["تنفيذ النسخ الاحتياطي في المستقبل"],
        "execution_results": [
            {"status": "failed", "label": "اختبار النسخ الاحتياطي"},
        ],
    }
    report = analyze_session(session)
    assert report["completed_work"] == ["إضافة نظام النسخ الاحتياطي", "تصميم خطة التحقق القادمة"]
    assert report["confirmed_achievements"] == []


def test_only_verified_execution_evidence_is_confirmed():
    from lab_v4_dev.memory.session_state import analyze_session

    report = analyze_session({
        "session_id": "evidence-2",
        "completed_work": ["وصف غير موثق للعمل"],
        "execution_results": [
            {"status": "success", "label": "إنشاء الملف", "executed": True},
            {"status": "failed", "label": "تشغيل الاختبار الفاشل"},
        ],
        "test_results": [
            {"status": "passed", "label": "اختبار القبول"},
        ],
    })
    assert report["confirmed_achievements"] == ["إنشاء الملف", "اختبار القبول"]
    assert "وصف غير موثق للعمل" not in report["confirmed_achievements"]
    assert "تشغيل الاختبار الفاشل" not in report["confirmed_achievements"]


def test_missing_confirmed_field_does_not_promote_completed_work():
    from lab_v4_dev.memory.session_state import analyze_session, build_session_restore_summary

    report = analyze_session({
        "session_id": "evidence-3",
        "completed_work": ["خطة مستقبلية للعمل على الجلسة"],
        "dialogue_state": {"exchange_archive": [
            {"target": "الجلسة أ", "user": "نص حوار لا يجب عرضه"},
        ]},
    })
    rendered = build_session_restore_summary({
        "session_id": "evidence-3",
        "completed_work": ["خطة مستقبلية للعمل على الجلسة"],
        "dialogue_state": {"exchange_archive": [
            {"target": "الجلسة أ", "user": "نص حوار لا يجب عرضه"},
        ]},
    })
    assert report["confirmed_achievements"] == []
    assert "4) أوصاف أعمال غير متحققة" in rendered
    assert "خطة مستقبلية للعمل على الجلسة" in rendered
    assert "نص حوار لا يجب عرضه" not in rendered
