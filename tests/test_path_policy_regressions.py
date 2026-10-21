import os

import pytest

from lab_v4_dev.core.project_context import CYBERLAB_ROOT, is_safe_project_path
from lab_v4_dev.recovery.path_policy import canonical_path, is_forbidden_system_path, is_within
from lab_v4_dev.recovery.permissions import FrozenZoneError, check_write


def test_system_path_checks_use_component_boundaries():
    assert is_forbidden_system_path("/etc/passwd")
    assert not is_forbidden_system_path("/etcetera/passwd")
    assert is_safe_project_path("/etcetera/passwd")


def test_absolute_frozen_zone_is_enforced():
    with pytest.raises(FrozenZoneError):
        check_write(os.path.join(CYBERLAB_ROOT, "tests", "test_example.py"))


def test_containment_resolves_symlinked_parent(tmp_path):
    outside, inside = tmp_path / "outside", tmp_path / "inside"
    outside.mkdir()
    inside.mkdir()
    link = inside / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert canonical_path(link / "new.txt") == canonical_path(outside / "new.txt")
    assert is_within(link / "new.txt", outside)
    assert not is_within(link / "new.txt", inside)


def test_snapshot_cannot_restore_a_different_target(tmp_path, monkeypatch):
    import lab_v4_dev.core.audit as audit
    import lab_v4_dev.recovery.snapshot as snapshot_module
    from lab_v4_dev.recovery.snapshot import take
    from lab_v4_dev.recovery.rollback import rollback

    monkeypatch.chdir(tmp_path)
    archive_dir = str(tmp_path / "archives" / "snapshots")
    import lab_v4_dev.recovery.rollback as rollback_module
    monkeypatch.setattr(snapshot_module, "SNAPSHOTS_DIR", archive_dir)
    monkeypatch.setattr(rollback_module, "SNAPSHOTS_DIR", archive_dir)
    monkeypatch.setattr(audit, "AUDIT_FILE", str(tmp_path / "execution_audit.json"))
    first = tmp_path / "project" / "first.txt"
    second = tmp_path / "project" / "second.txt"
    first.parent.mkdir(parents=True)
    first.write_text("first\n", encoding="utf-8")
    second.write_text("second\n", encoding="utf-8")
    snapshot = take(str(first))
    result = rollback(str(second), snapshot["snapshot"], trusted=True)
    assert result["status"] == "failed"
    assert result["reason"] == "snapshot_target_mismatch"
    assert second.read_text(encoding="utf-8") == "second\n"
