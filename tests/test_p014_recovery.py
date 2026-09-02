import os
from lab_v4_dev.recovery.snapshot import take, list_snapshots
from lab_v4_dev.recovery.safe_apply import safe_apply
from lab_v4_dev.recovery.rollback import rollback


def test_snapshot_and_safe_apply_and_rollback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # prepare file
    file_path = "project/foo.py"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("print('v1')\n")

    # take snapshot
    res = take(file_path)
    assert res["status"] == "ok"
    assert os.path.exists(res["snapshot"])

    snaps = list_snapshots(file_path)
    assert len(snaps) >= 1

    # safe_apply new content
    res2 = safe_apply(file_path, "print('v2')\n")
    assert res2["status"] == "ok"
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "v2" in content

    # rollback to snapshot (trusted=True default) should succeed
    rb = rollback(file_path, res["snapshot"], trusted=True)
    assert rb["status"] == "ok"
