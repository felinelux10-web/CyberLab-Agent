"""Runtime paths must not depend on the process working directory."""
import os
from pathlib import Path


def test_runtime_storage_paths_are_anchored_to_repository():
    from lab_v4_dev.core.state import STATE_FILE
    from lab_v4_dev.memory.db import DB_PATH, SCHEMA_PATH
    from lab_v4_dev.monitor.health_check import ROOT_DIR as HEALTH_ROOT
    from lab_v4_dev.cli.commands import ROOT_DIR as CLI_ROOT, CACHE_DIR

    repo_root = Path(__file__).resolve().parents[1]
    assert Path(STATE_FILE) == repo_root / "lab_v4_dev" / "cache" / "state.json"
    assert Path(DB_PATH) == repo_root / "lab_v4_dev" / "memory" / "agent.db"
    assert Path(SCHEMA_PATH) == repo_root / "lab_v4_dev" / "memory" / "schema.sql"
    assert HEALTH_ROOT == repo_root
    assert CLI_ROOT == repo_root
    assert CACHE_DIR == repo_root / "lab_v4_dev" / "cache"
    assert all(Path(value).is_absolute() for value in (STATE_FILE, DB_PATH, SCHEMA_PATH))


def test_startup_does_not_replace_existing_state():
    source = (Path(__file__).resolve().parents[1] / "run.py").read_text(encoding="utf-8")
    assert "if not os.path.exists(state_path):" in source
    assert 'open("lab_v4_dev/cache/state.json","w")' not in source
