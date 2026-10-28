import sqlite3


def test_health_check_does_not_require_optional_legacy_stable_tree(tmp_path, monkeypatch):
    from lab_v4_dev.monitor import health_check

    monkeypatch.setattr(health_check, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(health_check, "get_ram_mb", lambda: 10.0)
    memory_dir = tmp_path / "lab_v4_dev" / "memory"
    memory_dir.mkdir(parents=True)
    with sqlite3.connect(memory_dir / "agent.db") as conn:
        conn.execute("CREATE TABLE health_probe (id INTEGER)")

    class State:
        mode = "normal"

    result = health_check.check_health(State())

    assert result["db_ok"] is True
    assert result["stable_ok"] is True
    assert result["stable_status"] == "not_installed"
    assert result["healthy"] is True


def test_existing_legacy_stable_tree_still_requires_protected_memory_file(tmp_path, monkeypatch):
    from lab_v4_dev.monitor import health_check

    monkeypatch.setattr(health_check, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(health_check, "get_ram_mb", lambda: 10.0)
    memory_dir = tmp_path / "lab_v4_dev" / "memory"
    memory_dir.mkdir(parents=True)
    with sqlite3.connect(memory_dir / "agent.db") as conn:
        conn.execute("CREATE TABLE health_probe (id INTEGER)")
    (tmp_path / "stable").mkdir()

    class State:
        mode = "normal"

    result = health_check.check_health(State())

    assert result["stable_ok"] is False
    assert result["stable_status"] == "required_file_missing"
    assert result["healthy"] is False
