"""Runtime storage paths must not depend on the process working directory."""
import os
from pathlib import Path

import lab_v4_dev.core.execution_history as execution_history


def test_runtime_storage_paths_are_anchored_to_repository():
    from lab_v4_dev.core.audit import AUDIT_FILE
    from lab_v4_dev.core.sandbox_executor import ERROR_LOG, WORKSPACE
    from lab_v4_dev.config.provider_config import CONFIG_PATH
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
    assert Path(AUDIT_FILE) == repo_root / "execution_audit.json"
    assert Path(execution_history.HISTORY_FILE) == repo_root / "workspace" / "run_history"
    assert Path(ERROR_LOG) == repo_root / "workspace" / "error_log"
    assert Path(WORKSPACE) == repo_root / "workspace"
    assert Path(CONFIG_PATH) == repo_root / "lab_v4_dev" / "config" / "llm_provider.json"
    orchestrator_source = (repo_root / "lab_v4_dev" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert 'WORKSPACE_DIR = os.path.join(CYBERLAB_ROOT, "workspace")' in orchestrator_source
    assert 'os.listdir("workspace/scripts")' not in orchestrator_source
    assert 'os.path.exists("releases")' not in orchestrator_source
    assert '"workspace/external_index/dependency_graph.json"' not in orchestrator_source
    assert all(Path(value).is_absolute() for value in (
        STATE_FILE, DB_PATH, SCHEMA_PATH, AUDIT_FILE,
        execution_history.HISTORY_FILE, ERROR_LOG, str(CONFIG_PATH),
    ))


def test_execution_history_is_independent_of_process_working_directory(tmp_path, monkeypatch):
    history_dir = tmp_path / "agent-data" / "run_history"
    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()

    monkeypatch.setattr(execution_history, "HISTORY_FILE", str(history_dir))
    monkeypatch.chdir(unrelated_cwd)

    saved = execution_history.save_run("sample.py", "success", 0.25)
    history = execution_history.get_history(10)

    assert saved["script"] == "sample.py"
    assert len(history) == 1
    assert history[0]["script"] == "sample.py"
    assert history_dir.is_dir()


def test_startup_does_not_replace_existing_state():
    source = (Path(__file__).resolve().parents[1] / "run.py").read_text(encoding="utf-8")
    assert "if not os.path.exists(state_path):" in source
    assert 'open("lab_v4_dev/cache/state.json","w")' not in source
