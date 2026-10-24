from types import SimpleNamespace

import lab_v4_dev.conversation.conversation_manager as manager_module
import lab_v4_dev.llm.prompt_builder as prompt_builder
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class LocalOnlyOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, parsed, kwargs))
        return {"status": "success", "text": "unexpected execution response"}


def test_project_progress_question_uses_saved_local_state(monkeypatch):
    monkeypatch.setattr(
        "lab_v4_dev.awareness.project_knowledge.get_project_state",
        lambda: {
            "version": "5.9.13-dev",
            "current_focus": "إصلاح مسار الرد المحلي",
            "last_goal": "توحيد توجيه الحوار",
            "last_step": "اختبار أسئلة حالة المشروع",
            "active": ["إصلاح تصنيف النية"],
            "planned": ["اختبارات رجعية"],
            "completed_count": 7,
        },
    )
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("project progress must be answered from local state")
        ),
    )
    orchestrator = LocalOnlyOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("أين توقف العمل في مشروع cyberlab_agent؟")

    assert result["status"] == "success"
    assert result["source"] == "local_project_knowledge"
    assert "إصلاح مسار الرد المحلي" in result["text"]
    assert "اختبارات رجعية" in result["text"]
    assert "ليست إثباتًا على حالة تشغيل لحظية" in result["text"]
    assert orchestrator.calls == []


def test_project_plan_uses_local_state_and_does_not_fall_back_to_generic_plan(monkeypatch):
    monkeypatch.setattr(
        "lab_v4_dev.awareness.project_knowledge.get_project_state",
        lambda: {
            "current_focus": "توحيد طبقة الكتابة",
            "last_goal": "منع الكتابة غير الآمنة",
            "last_step": "التحقق من الاختبارات",
            "active": [],
            "planned": ["اختبار سياسة الكتابة الحقيقية"],
            "completed_count": 3,
        },
    )
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("project plan must use local project state")
        ),
    )
    orchestrator = LocalOnlyOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager.process("ما هي خطة العمل في مشروع cyberlab_agent؟")

    assert result["status"] == "success"
    assert result["source"] == "local_project_knowledge"
    assert "توحيد طبقة الكتابة" in result["text"]
    assert "اختبار سياسة الكتابة الحقيقية" in result["text"]
    assert orchestrator.calls == []


def test_empty_cached_project_index_does_not_claim_there_are_zero_source_files(monkeypatch):
    monkeypatch.setattr(prompt_builder, "_load_index", lambda: {"files": []})
    monkeypatch.setattr(
        prompt_builder,
        "_load_roadmap",
        lambda: {
            "version": "5.9.13-dev",
            "current_focus": "إصلاح الرد المحلي",
            "active": ["إصلاح توجيه الحوار"],
            "planned": ["اختبارات رجعية"],
            "completed": ["توحيد طبقة الكتابة"],
        },
    )
    monkeypatch.setattr(
        prompt_builder,
        "get_active_project",
        lambda: SimpleNamespace(name="CyberLab Agent"),
    )

    context = prompt_builder.build_project_context(
        project_scope="CURRENT_PROJECT",
        question="أين توقف العمل في مشروع cyberlab_agent؟",
    )

    assert "فهرس الملفات المحفوظ لا يحتوي على قائمة قابلة للاعتماد" in context
    assert "لا يعني أن المشروع لا يحتوي على ملفات مصدر" in context
    assert "التركيز الحالي: إصلاح الرد المحلي" in context
    assert "عدد ملفات Python: 0" not in context
