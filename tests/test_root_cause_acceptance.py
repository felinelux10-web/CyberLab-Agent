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
