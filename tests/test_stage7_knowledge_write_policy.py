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

    result = project_scanner.run(str(tmp_path))

    assert result["total_files"] >= 0
    assert calls[0][2] == "project_scanner:write_inventory"
    assert json.loads(output.read_text(encoding="utf-8"))["total_files"] == result["total_files"]


def test_dependency_map_writes_through_safe_write(monkeypatch, tmp_path):
    calls = []
    output = tmp_path / "dependency_map.json"
    monkeypatch.setattr(dependency_map, "_map_file", lambda: str(output))
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
