"""
CyberLab Agent
Series 3

Project Loader
"""

from lab_v4_dev.project_registry.registry import (
    load_registry,
    get_project,
)


def get_active_project():
    """
    يعيد المشروع النشط من الـ Registry.
    """
    registry = load_registry()
    return registry.get("active_project")




def has_active_project() -> bool:
    """
    يتحقق من وجود مشروع نشط.
    """
    return get_active_project() is not None




def list_registered_projects():
    """
    يعيد جميع المشاريع المسجلة.
    """
    registry = load_registry()
    return registry.get("projects", [])


def load_project(root: str):
    """
    يحمل مشروعاً مسجلاً بواسطة root.
    """
    return get_project(root)
