import os


def _isolate(monkeypatch, tmp_path):
    import lab_v4_dev.core.audit as audit
    import lab_v4_dev.recovery.snapshot as snapshot_module
    archive_dir = str(tmp_path / "archive" / "snapshots")
    import lab_v4_dev.recovery.rollback as rollback_module
    monkeypatch.setattr(snapshot_module, "SNAPSHOTS_DIR", archive_dir)
    monkeypatch.setattr(rollback_module, "SNAPSHOTS_DIR", archive_dir)
    monkeypatch.setattr(audit, "AUDIT_FILE", str(tmp_path / "execution_audit.json"))


def test_snapshot_names_do_not_collide_for_distinct_paths(tmp_path, monkeypatch):
    from lab_v4_dev.recovery.snapshot import take
    from lab_v4_dev.recovery.rollback import rollback

    _isolate(monkeypatch, tmp_path)
    first = tmp_path / "a.b" / "c.txt"
    second = tmp_path / "a" / "b.c.txt"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    snap = take(str(first))
    result = rollback(str(second), snap["snapshot"])

    assert result["status"] == "failed"
    assert result["reason"] == "snapshot_target_mismatch"
    assert second.read_text(encoding="utf-8") == "second"


def test_snapshot_archive_is_independent_of_working_directory(tmp_path, monkeypatch):
    from lab_v4_dev.recovery.snapshot import take
    from lab_v4_dev.recovery.rollback import rollback
    import lab_v4_dev.recovery.snapshot as snapshot_module

    _isolate(monkeypatch, tmp_path)
    target = tmp_path / "project" / "sample.txt"
    target.parent.mkdir()
    target.write_text("before", encoding="utf-8")
    snapshot = take(str(target))
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    target.write_text("after", encoding="utf-8")

    result = rollback(str(target), snapshot["snapshot"])

    assert result["status"] == "ok"
    assert target.read_text(encoding="utf-8") == "before"
    assert os.path.isabs(snapshot_module.SNAPSHOTS_DIR)


def test_rollback_of_new_file_restores_absence(tmp_path, monkeypatch):
    from lab_v4_dev.recovery.snapshot import take
    from lab_v4_dev.recovery.rollback import rollback

    _isolate(monkeypatch, tmp_path)
    target = tmp_path / "project" / "new.py"
    target.parent.mkdir()
    snapshot = take(str(target))
    target.write_text("created later", encoding="utf-8")

    result = rollback(str(target), snapshot["snapshot"])

    assert result["status"] == "ok"
    assert not target.exists()
