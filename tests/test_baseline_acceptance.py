import ast
from pathlib import Path

from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.core.orchestrator import Orchestrator
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent


def test_greeting_variant_is_not_stop_or_unsupported():
    result = parse("مهلا")
    assert result["intent"] == Intent.PERSONAL_CHAT
    assert result["intent"] not in {Intent.STOP, Intent.UNSUPPORTED}


def test_project_name_question_uses_project_registry_intent():
    result = parse("ما أسماء المشاريع التي تظهر عندك؟")
    assert result["intent"] == Intent.PROJECT_INDEX


def test_workspace_script_is_searchable_as_a_file_target(tmp_path, monkeypatch):
    root = tmp_path / "project"
    script = root / "workspace" / "scripts" / "game.py"
    script.parent.mkdir(parents=True)
    script.write_text("def start_game():\n    return 1\n", encoding="utf-8")

    import lab_v4_dev.core.symbol_resolver as resolver
    monkeypatch.setattr(resolver, "get_active_project_root", lambda: str(root))

    result = resolver.resolve("عدّل الدالة start_game", "")
    assert result["found"] is True
    assert Path(result["file"]).resolve() == script.resolve()
    assert result["symbol"] == "start_game"


def test_modify_uses_current_generated_file_without_named_symbol(tmp_path, monkeypatch):
    target = tmp_path / "workspace" / "scripts" / "game.py"
    target.parent.mkdir(parents=True)
    original = "print('plain game')\n"
    target.write_text(original, encoding="utf-8")

    class Agent:
        db = None

    context = ContextStore()
    context.current_file = str(target)
    orchestrator = Orchestrator(Agent(), context=context)

    monkeypatch.setattr(
        "lab_v4_dev.core.code_engine.modify_code",
        lambda code, instruction: {
            "status": "success",
            "code": code + "print('colored')\n",
            "explanation": "added colors",
        },
    )

    class Pipeline:
        def __init__(self, _db):
            pass

        def execute(self, _plan, modifications):
            for path, content in modifications.items():
                Path(path).write_text(content, encoding="utf-8")
            return {"status": "success"}

    monkeypatch.setattr("lab_v4_dev.core.orchestrator.SafePipeline", Pipeline)

    result = orchestrator._route(
        Intent.MODIFY_CODE,
        "",
        "general",
        "أضف ألوانًا إلى اللعبة",
    )

    assert result["status"] == "success"
    assert target.read_text(encoding="utf-8") != original
    assert "colored" in target.read_text(encoding="utf-8")


def test_game_generation_is_interactive_and_syntax_valid(tmp_path, monkeypatch):
    import lab_v4_dev.core.code_engine as engine

    monkeypatch.setattr(engine, "WORKSPACE", str(tmp_path / "workspace"))
    result = engine.generate_code("اكتب لعبة بسيطة لكن يجب أن تشتغل اللعبة")

    assert result["status"] == "success"
    assert "input(" in result["code"]
    assert "attempts" in result["code"]
    assert "أكبر" in result["code"] and "أصغر" in result["code"]
    ast.parse(result["code"])
    assert Path(result["saved_to"]).exists()


def test_color_request_has_deterministic_valid_fallback():
    from lab_v4_dev.core.code_engine import modify_code

    result = modify_code("print('hello')\n", "إضافة ألوان إلى اللعبة")
    assert result["status"] == "success"
    assert "colorize" in result["code"]
    ast.parse(result["code"])
