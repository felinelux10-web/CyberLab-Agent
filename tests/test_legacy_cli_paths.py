"""Prevent active CLI commands from reading/writing the deprecated tree."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_shortcuts_and_help_use_active_tree():
    source = (ROOT / "lab_v4_dev/cli/commands.py").read_text(encoding="utf-8")
    assert '"ls"      : "شغّل ls lab_v4_dev"' in source
    assert "ls             : list lab_v4_dev" in source


def test_cli_search_scans_active_tree():
    source = (ROOT / "lab_v4_dev/cli/commands.py").read_text(encoding="utf-8")
    assert 'os.walk("lab_v4_dev")' in source
    assert 'os.walk("lab_v4")' not in source


def test_cli_generated_files_use_active_cache():
    source = (ROOT / "lab_v4_dev/cli/commands.py").read_text(encoding="utf-8")
    assert 'path = f"lab_v4_dev/cache/report_' in source
    assert 'path = f"lab_v4_dev/cache/draft_' in source
    assert 'path = f"lab_v4/cache/' not in source
