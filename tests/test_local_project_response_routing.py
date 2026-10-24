from types import SimpleNamespace

import lab_v4_dev.conversation.conversation_manager as manager_module
import lab_v4_dev.llm.prompt_builder as prompt_builder
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory
from lab_v4_dev.conversation.semantic_contract import ContextTransition
from lab_v4_dev.intent.intents import Intent


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
    monkeypatch.setattr(prompt_builder, "_load_index", lambda: {"files": [], "version": 2, "total_files": 0})
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


def test_project_scoped_continuation_cannot_be_hijacked_by_stale_technical_topic(monkeypatch):
    monkeypatch.setattr(
        "lab_v4_dev.awareness.project_knowledge.get_project_state",
        lambda: {
            "current_focus": "إصلاح الرد المحلي",
            "last_goal": "تصحيح مسارات الحوار",
            "last_step": "اختبار استمرار سياق المشروع",
            "active": ["توجيه نية الرسالة"],
            "planned": ["تغطية أخطاء الحوار"],
            "completed_count": 2,
        },
    )
    monkeypatch.setattr(
        manager_module,
        "gateway_ask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("project-scoped continuation must not drift to a stale technical topic")
        ),
    )
    orchestrator = LocalOnlyOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    memory.state.last_topic = "Buffer Overflow"
    memory.state.last_entity_type = "CONCEPT"
    memory.state.exchange_archive = [{
        "session_id": memory.state.session_id,
        "user": "اشرح Buffer Overflow",
        "assistant": "شرح تقني قديم",
        "target": "Buffer Overflow",
        "intent": "cyber_explain",
        "conversation_domain": "technical",
        "context_kind": "dialogue",
    }]
    manager = ConversationManager(orchestrator, memory)

    result = manager.process("أكمل الشرح في نفس سؤال مشروع cyberlab_agent")

    assert result["status"] == "success"
    assert result["source"] == "local_project_knowledge"
    assert "إصلاح الرد المحلي" in result["text"]
    assert "Buffer Overflow" not in result["text"]
    assert orchestrator.calls == []


def test_bare_follow_up_keeps_the_project_branch_after_a_local_progress_reply(monkeypatch):
    monkeypatch.setattr(
        "lab_v4_dev.awareness.project_knowledge.get_project_state",
        lambda: {
            "current_focus": "إصلاح الرد المحلي",
            "last_goal": "تصحيح مسارات الحوار",
            "last_step": "اختبار متابعة المشروع",
            "active": ["توجيه النية"],
            "planned": ["اختبارات رجعية"],
            "completed_count": 2,
        },
    )
    monkeypatch.setattr(prompt_builder, "_load_index", lambda: {"files": []})
    monkeypatch.setattr(
        prompt_builder,
        "_load_roadmap",
        lambda: {
            "version": "5.9.13-dev",
            "current_focus": "إصلاح الرد المحلي",
            "active": ["توجيه النية"],
            "planned": ["اختبارات رجعية"],
            "completed": ["توحيد طبقة الكتابة"],
        },
    )
    monkeypatch.setattr(
        prompt_builder,
        "get_active_project",
        lambda: SimpleNamespace(name="CyberLab Agent"),
    )
    prompts = []

    def fake_gateway(prompt, **kwargs):
        prompts.append((str(prompt), str(kwargs.get("system") or "")))
        return {"status": "success", "text": "متابعة من سياق المشروع", "provider_used": "test"}

    monkeypatch.setattr(manager_module, "gateway_ask", fake_gateway)
    orchestrator = LocalOnlyOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    memory.state.last_topic = "Buffer Overflow"
    memory.state.last_entity_type = "CONCEPT"
    manager = ConversationManager(orchestrator, memory)

    first = manager.process("أين توقف العمل في مشروع cyberlab_agent؟")
    assert first["source"] == "local_project_knowledge"

    follow_up = manager.process("أكمل")

    assert follow_up["status"] == "success"
    assert follow_up["text"] == "متابعة من سياق المشروع"
    assert prompts
    assert "إصلاح الرد المحلي" in prompts[-1][1]
    assert "Buffer Overflow" not in prompts[-1][0] + prompts[-1][1]
    assert orchestrator.calls == []


def test_explicit_project_execution_request_still_uses_orchestrator():
    orchestrator = LocalOnlyOrchestrator()
    manager = ConversationManager(orchestrator, DialogueMemory(orchestrator.context))

    result = manager._dispatch(
        "شغل الاختبارات",
        "FOLLOW_UP",
        {
            "intent": Intent.CYBER_EXPLAIN,
            "target": "CyberLab Agent",
            "entity_type": "PROJECT",
            "conversation_domain": "project",
            "conversation_act": "CONVERSATION_CONTINUATION",
        },
        user_question="شغل الاختبارات",
        context_transition=ContextTransition.CONTINUE.value,
    )

    assert result["text"] == "unexpected execution response"
    assert len(orchestrator.calls) == 1

