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


def test_orchestrator_returns_collection_report_locally_without_provider(monkeypatch):
    from lab_v4_dev.core.orchestrator import Orchestrator
    from lab_v4_dev.intent.intents import Intent

    art = _dialogue(
        "saved-art-route",
        "الفن التجريدي والنقش البارز",
        "ما الفرق بين الفن التجريدي والنقش البارز؟",
        "يرتبط الفرق بأسلوب معالجة الشكل والسطح.",
        "الفن التجريدي والنقش البارز",
    )
    index = [art]
    monkeypatch.setattr(session_state, "get_session_index", lambda: index)
    monkeypatch.setattr(session_state, "get_session_by_id", lambda session_id: art if session_id == art["session_id"] else {})
    monkeypatch.setattr(
        "lab_v4_dev.core.orchestrator.ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("all-sessions report must not require a provider")
        ),
    )
    selector = session_state.session_selector("اكتب تقرير مفصل لجميع الجلسات")
    orchestrator = Orchestrator(SimpleNamespace(runtime=None))

    result = orchestrator.handle(
        "اكتب تقرير مفصل لجميع الجلسات",
        parsed={
            "intent": Intent.SESSION_RESTORE,
            "target": "",
            "context": "system",
            "session_selector": selector,
        },
    )

    assert result["status"] == "success"
    assert result["source"] == "local_all_sessions_report"
    assert result["output_kind"] == "report"
    assert result["context_action"] == "read_only_report"
    assert result["session_count"] == 1
    assert "الفن التجريدي والنقش البارز" in result["text"]


def test_route_decision_preserves_report_contract_for_saved_collection():
    from lab_v4_dev.context.context_store import ContextStore
    from lab_v4_dev.conversation.conversation_manager import ConversationManager
    from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
    from lab_v4_dev.conversation.semantic_contract import ContextTransition
    from lab_v4_dev.intent.intents import Intent

    context = ContextStore()
    manager = ConversationManager(SimpleNamespace(context=context), DialogueMemory(context))
    decision = manager.finalize_route(
        parsed={"intent": Intent.SESSION_RESTORE, "output_kind": "report"},
        selected_session={
            "kind": "list",
            "report_mode": "full",
            "output_kind": "report",
        },
        saved_session_request=True,
        selected_saved_session_id=None,
        transition=ContextTransition.NEW_INDEPENDENT,
    )

    assert decision.route == "L-SESSION"
    assert decision.session_scope == "none"
    assert decision.output_kind == "report"
    assert decision.provider_allowed is False
    assert decision.metadata["evidence_collection"] == "saved_sessions"


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
