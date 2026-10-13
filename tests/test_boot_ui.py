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
    assert any("[OK]" in line for line in output)
    assert "STATUS: READY" in output


def test_boot_dashboard_marks_failed_component(capsys):
    ui = BootUI()
    ui.start()
    ui.row("DATABASE", "Integrity check failed", "FAIL")

    output = capsys.readouterr().out
    assert "[X]" in output
    assert "Integrity check failed" in output
