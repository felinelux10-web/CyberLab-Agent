# CyberLab Agent
# Series 3
# Project Registry

from pathlib import Path
import json

REGISTRY_FILE = Path("project_data/project_registry.json")


def load_registry():
    if not REGISTRY_FILE.exists():
        return {}

    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_registry(data):
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )




def project_exists(root: str) -> bool:
    data = load_registry()

    for project in data.get("projects", []):
        if project.get("root") == root:
            return True

    return False




def get_project(root: str):
    data = load_registry()

    for project in data.get("projects", []):
        if project.get("root") == root:
            return project

    return None


def get_project_by_name(name: str):
    """يعيد المشروع المسجل المطابق للاسم، مع تفضيل المشروع من نوع agent عند التكرار."""
    data = load_registry()
    name = str(name).strip()

    matches = [
        project for project in data.get("projects", [])
        if project.get("name") == name
    ]

    if not matches:
        return None

    # cyberlab_agent هو جذر المشروع، وليس lab_v4_dev.
    if name == "cyberlab_agent":
        from lab_v4_dev.core.project_context import CYBERLAB_ROOT
        for project in matches:
            if project.get("root") == CYBERLAB_ROOT:
                return project

    for project in matches:
        if project.get("type") == "agent":
            return project

    return matches[0]




def update_project(root: str, updates: dict) -> bool:
    data = load_registry()

    for project in data.get("projects", []):
        if project.get("root") == root:
            project.update(updates)
            save_registry(data)
            return True

    return False




def remove_project(root: str) -> bool:
    data = load_registry()

    projects = data.get("projects", [])

    new_projects = [p for p in projects if p.get("root") != root]

    if len(new_projects) == len(projects):
        return False

    data["projects"] = new_projects
    save_registry(data)

    return True


def register_project(project: dict):
    data = load_registry()

    projects = data.setdefault("projects", [])

    root = project.get("root")

    if not any(p.get("root") == root for p in projects):
        projects.append(project)

    save_registry(data)
