from lab_v4_dev.core.boot_ui import BootUI


def test_boot_dashboard_has_consistent_borders_and_ready_state(capsys):
    ui = BootUI()
    ui.start()
    ui.row("DATABASE", "Connection and integrity OK")
    ui.ready()

    output = capsys.readouterr().out.splitlines()
    borders = [line for line in output if line.startswith(("┌", "├", "└"))]
    assert borders
    assert len({len(line) for line in borders}) == 1
    assert any("CYBERLAB AGENT" in line for line in output)
    assert any("[✓]" in line for line in output)
    assert any("STATUS: READY" in line for line in output)


def test_boot_dashboard_marks_failed_component(capsys):
    ui = BootUI()
    ui.start()
    ui.row("DATABASE", "Integrity check failed", "FAIL")

    output = capsys.readouterr().out
    assert "[X]" in output
    assert "Integrity check" in output
    assert "failed" in output


def test_boot_dashboard_marks_paused_sessions_distinctly(capsys):
    ui = BootUI()
    ui.start()
    ui.section("PENDING WORK SESSIONS", "PENDING")
    ui.row("STATE", "paused", "PENDING")

    output = capsys.readouterr().out
    assert "PENDING WORK SESSIONS" in output
    assert "[↻]" in output


def test_command_prompt_is_labeled_and_separated(capsys, monkeypatch):
    ui = BootUI()
    monkeypatch.setattr("builtins.input", lambda: "hello")
    assert ui.prompt() == "hello"
    output = capsys.readouterr().out
    assert "CYBERLAB" in output
    assert "اكتب الأمر هنا" in output
