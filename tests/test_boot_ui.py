import io

from lab_v4_dev.core.boot_ui import BootUI
from lab_v4_dev.core.agent import Agent


def test_startup_uses_default_language_and_bordered_status_table(capsys):
    ui = BootUI()
    ui.start()
    ui.row("DATABASE", "Connection and integrity OK")
    ui.ready()

    output = capsys.readouterr().out
    assert "CYBERLAB AGENT" in output
    assert "STARTUP STATUS" in output
    assert "STATUS" in output
    assert "COMPONENT" in output
    assert "DETAILS" in output
    assert "STATUS: READY" not in output
    assert "AGENT READY" in output
    assert "╔" in output or "║" in output


def test_status_rows_have_spacing_and_wrapped_text_is_aligned(capsys):
    ui = BootUI()
    ui.width = 34
    ui.row("DATABASE", "Connection and integrity check passed successfully")
    ui.row("HEALTH", "System checks passed")

    lines = capsys.readouterr().out.splitlines()
    first_row = next(i for i, line in enumerate(lines) if "DATABASE" in line)
    continuation = lines[first_row + 1]
    next_row = next(i for i, line in enumerate(lines) if "HEALTH" in line)
    assert continuation.startswith("║")
    assert "│" in continuation
    assert "╠" in lines[next_row - 1]


def test_failed_component_has_red_state_marker_text(capsys):
    ui = BootUI()
    ui.row("DATABASE", "Integrity check failed", "FAIL")
    output = capsys.readouterr().out
    assert "●" in output
    assert "DATABASE" in output
    assert "Integrity check" in output
    assert "failed" in output


def test_prompt_uses_only_cyberlab_identity_and_separator(capsys, monkeypatch):
    ui = BootUI()
    seen_prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": seen_prompts.append(prompt) or "")
    result = ui.prompt()
    output = capsys.readouterr().out
    assert result == ""
    assert seen_prompts == ["> "]
    assert "CYBERLAB" in output
    assert "✦" in output
    assert "─" * 20 in output
    assert "اكتب الأمر هنا" not in output
    assert "اكتب الأوامر" not in output


def test_saved_sessions_show_short_title_and_expand_on_selection(capsys):
    agent = Agent.__new__(Agent)
    agent._pending_work_sessions = [{
        "number": 1,
        "report": {
            "session_id": "session-1",
            "topic": "SQL Injection — دراسة تفصيلية",
            "active_goal": "اختبار معالجة المدخلات",
            "status": "paused",
            "last_updated": "2026-10-13",
            "last_completed_step": "تحليل نقطة الدخول",
            "current_state": "توقفت قبل كتابة الاختبارات",
            "next_step": "إضافة اختبارات تحقق",
        },
        "recoverable": False,
    }]

    assert agent.show_pending_session("session 1") is True
    output = capsys.readouterr().out
    assert "تفاصيل الجلسة 1" in output
    assert "توقفت قبل كتابة الاختبارات" in output
    assert "للمراجعة فقط" in output
    assert "╔" in output


def test_session_cards_keep_each_summary_in_a_separate_frame(capsys):
    ui = BootUI()
    ui.section("SAVED SESSIONS")
    ui.session_card(1, "موضوع الكتب — REVIEW ONLY", "WARN")
    ui.session_card(2, "موضوع الفن — DIALOGUE SAVED", "OK")
    ui.close_section()

    output = capsys.readouterr().out
    assert "SESSION 1" in output
    assert "SESSION 2" in output
    assert "موضوع الكتب" in output
    assert "موضوع الفن" in output
    assert output.count("╠") >= 3


def test_non_session_command_is_not_consumed():
    agent = Agent.__new__(Agent)
    agent._pending_work_sessions = []
    assert agent.show_pending_session("مرحبا") is False

def test_multiline_terminal_paste_is_one_logical_message(monkeypatch):
    import lab_v4_dev.core.boot_ui as boot_ui_module

    ui = BootUI()

    class FakeTTY:
        def __init__(self):
            self.lines = iter(["2. سؤال تقني\n", "\n", "3. تصحيح افتراض\n"])

        def isatty(self):
            return True

        def readline(self):
            return next(self.lines, "")

    stream = FakeTTY()
    monkeypatch.setattr(boot_ui_module.sys, "stdin", stream)
    readiness = iter([
        ([stream], [], []),
        ([stream], [], []),
        ([stream], [], []),
        ([], [], []),
    ])
    monkeypatch.setattr(
        boot_ui_module.select,
        "select",
        lambda *args, **kwargs: next(readiness),
    )

    result = ui._read_pasted_continuation("1. بداية الحوار")

    assert result == "1. بداية الحوار\n2. سؤال تقني\n\n3. تصحيح افتراض"


def test_single_line_prompt_remains_single_line_when_stdin_is_not_tty(monkeypatch):
    import io
    import lab_v4_dev.core.boot_ui as boot_ui_module

    monkeypatch.setattr(boot_ui_module.sys, "stdin", io.StringIO("ignored"))
    ui = BootUI()
    assert ui._read_pasted_continuation("مرحبا") == "مرحبا"
