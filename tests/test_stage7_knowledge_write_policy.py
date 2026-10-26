import json
from pathlib import Path

import lab_v4_dev.awareness.dependency_map as dependency_map
import lab_v4_dev.awareness.knowledge_base as knowledge_base
import lab_v4_dev.project_knowledge.project_scanner as project_scanner


def fake_safe_write(calls):
    def write(path, content, reason=""):
        calls.append((str(path), content, reason))
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"status": "success", "path": str(target)}

    return write


def test_project_scanner_writes_inventory_through_safe_write(monkeypatch, tmp_path):
    calls = []
    output = tmp_path / "inventory.json"
    monkeypatch.setattr(project_scanner, "OUTPUT_FILE", str(output))
    monkeypatch.setattr("lab_v4_dev.core.safe_io.safe_write", fake_safe_write(calls))
    marker = tmp_path / "expected_project.py"
    marker.write_text("EXPECTED_PROJECT_MARKER = True\n", encoding="utf-8")

    result = project_scanner.run(str(tmp_path))

    assert result["project_root"] == str(tmp_path.resolve())
    assert "expected_project.py" in {item["path"] for item in result["files"]}
    assert calls[0][2] == "project_scanner:write_inventory"
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["project_root"] == str(tmp_path.resolve())
    assert saved["total_files"] == result["total_files"]


def test_dependency_map_writes_through_safe_write(monkeypatch, tmp_path):
    calls = []
    output = tmp_path / "dependency_map.json"
    monkeypatch.setattr(dependency_map, "_map_file", lambda _base_dir=None: str(output))
    monkeypatch.setattr(
        dependency_map,
        "build_dependency_map",
        lambda _base_dir: {"main.py": {"imports": [], "imported_by": []}},
    )
    monkeypatch.setattr("lab_v4_dev.core.safe_io.safe_write", fake_safe_write(calls))

    result = dependency_map.save_map(str(tmp_path))

    assert result == str(output)
    assert calls[0][2] == "dependency_map:save_map"
    assert json.loads(output.read_text(encoding="utf-8"))["main.py"]["imports"] == []


def test_knowledge_base_save_uses_safe_write(monkeypatch, tmp_path):
    calls = []
    output = tmp_path / "knowledge.json"
    monkeypatch.setattr(knowledge_base, "_kb_path", lambda: str(output))
    monkeypatch.setattr("lab_v4_dev.core.safe_io.safe_write", fake_safe_write(calls))

    knowledge_base._save({"schema_version": 2, "records": {}})

    assert calls[0][2] == "knowledge_base:save"
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 2



def test_project_index_is_saved_for_the_requested_project(tmp_path, monkeypatch):
    from lab_v4_dev.awareness import project_index

    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "alpha.py").write_text("def alpha():\n    return 'A'\n", encoding="utf-8")
    (project_b / "beta.py").write_text("def beta():\n    return 'B'\n", encoding="utf-8")

    monkeypatch.setattr(
        project_index,
        "project_index_dir",
        lambda root: str(tmp_path / "indices" / Path(root).name),
    )
    calls = []
    monkeypatch.setattr("lab_v4_dev.core.safe_io.safe_write", fake_safe_write(calls))

    saved_a = Path(project_index.save_index(str(project_a)))
    saved_b = Path(project_index.save_index(str(project_b)))

    assert saved_a == tmp_path / "indices" / "project_a" / "project_index.json"
    assert saved_b == tmp_path / "indices" / "project_b" / "project_index.json"
    assert [call[2] for call in calls] == [
        "project_index:save_index", "project_index:save_index"
    ]
    assert "alpha.py" in json.loads(saved_a.read_text(encoding="utf-8"))
    assert "beta.py" in json.loads(saved_b.read_text(encoding="utf-8"))
    assert "beta.py" not in json.loads(saved_a.read_text(encoding="utf-8"))


def test_dependency_map_is_saved_for_the_requested_project(tmp_path, monkeypatch):
    calls = []
    active_root = tmp_path / "active_project"
    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    for root in (active_root, project_a, project_b):
        root.mkdir()
    monkeypatch.setattr(
        dependency_map,
        "_map_file",
        lambda base_dir=None: str(
            tmp_path / "indices" / Path(base_dir or active_root).name / "dependency_map.json"
        ),
    )
    monkeypatch.setattr(
        dependency_map,
        "build_dependency_map",
        lambda base_dir: {Path(base_dir).name: {"imports": [], "imported_by": []}},
    )
    monkeypatch.setattr("lab_v4_dev.core.safe_io.safe_write", fake_safe_write(calls))

    path_a = Path(dependency_map.save_map(str(project_a)))
    path_b = Path(dependency_map.save_map(str(project_b)))

    assert path_a == tmp_path / "indices" / "project_a" / "dependency_map.json"
    assert path_b == tmp_path / "indices" / "project_b" / "dependency_map.json"
    assert "project_a" in json.loads(path_a.read_text(encoding="utf-8"))
    assert "project_b" in json.loads(path_b.read_text(encoding="utf-8"))


def test_project_index_directory_is_allowed_by_safe_write_policy(tmp_path):
    import lab_v4_dev.core.safe_io as safe_io
    from lab_v4_dev.core.project_context import project_index_dir

    index_dir = project_index_dir(str(tmp_path / "external_project"))
    workspace = Path(safe_io.PROJECT_ROOT) / "workspace"

    assert Path(index_dir).is_relative_to(workspace)
    assert safe_io._is_allowed(str(Path(index_dir) / "project_index.json"))
