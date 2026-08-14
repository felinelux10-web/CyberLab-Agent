"""
v5.4.1 — Project Context Layer
نقطة وصول موحّدة لـ "المشروع النشط حالياً" - يسمح للوكيل
بالعمل على مشاريع متعددة بدلاً من نفسه فقط.
"""
import os
import hashlib
from datetime import datetime
from lab_v4_dev.project_registry.registry import (
    load_registry,
    save_registry,
    register_project,
)
from lab_v4_dev.project_registry.project_loader import (
    get_active_project as loader_get_active_project,
)

CYBERLAB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

FORBIDDEN_PREFIXES = ["/etc", "/system", "/proc", "/dev", "/sys", "/root"]


def is_safe_project_path(path: str) -> bool:
    """يتحقق أن المسار آمن للعمل عليه (ليس مسار نظام حساس)"""
    abs_path = os.path.abspath(path)
    return not any(abs_path.startswith(p) for p in FORBIDDEN_PREFIXES)


def project_index_dir(project_root: str) -> str:
    """مجلد فهرسة هذا المشروع - داخل مساحة عمل الوكيل، لا داخل المشروع نفسه"""
    h = hashlib.md5(os.path.abspath(project_root).encode()).hexdigest()[:10]
    return os.path.join(CYBERLAB_ROOT, "project_indices", h)


class ProjectContext:
    """يمثل المشروع النشط حالياً"""

    def __init__(self, root: str = None, name: str = None, ptype: str = "unknown"):
        self.root = os.path.abspath(root) if root else CYBERLAB_ROOT
        self.name = name or os.path.basename(self.root)
        self.type = ptype
        self.last_scan = None

    def to_dict(self) -> dict:
        return {
            "root": self.root, "name": self.name,
            "type": self.type, "last_scan": self.last_scan,
        }

    def index_dir(self) -> str:
        return project_index_dir(self.root)


# استرجاع آخر مشروع نشط إن وجد
_loaded = loader_get_active_project()

if _loaded:
    _active_project = ProjectContext(
        root=_loaded["root"],
        name=_loaded.get("name"),
        ptype=_loaded.get("type", "unknown"),
    )
else:
    # المشروع الافتراضي = cyberlab_agent
    _active_project = ProjectContext(
        root=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        name="cyberlab_agent",
        ptype="agent",
    )


def get_active_project() -> ProjectContext:
    return _active_project


def get_active_project_root() -> str:
    return _active_project.root


def set_active_project(root: str) -> dict:
    """يبدّل المشروع النشط - مع فحوصات أمان"""
    global _active_project
    abs_root = os.path.abspath(os.path.expanduser(root))

    if not os.path.exists(abs_root):
        return {"status": "error", "message": f"المسار غير موجود: {abs_root}"}
    if not os.path.isdir(abs_root):
        return {"status": "error", "message": f"ليس مجلداً: {abs_root}"}
    if not is_safe_project_path(abs_root):
        return {"status": "error", "message": f"مسار غير مسموح (نظام): {abs_root}"}

    _active_project = ProjectContext(root=abs_root)

    registry = load_registry()
    registry["active_project"] = _active_project.to_dict()
    save_registry(registry)

    register_project(_active_project.to_dict())

    return {"status": "success", "project": _active_project.to_dict()}