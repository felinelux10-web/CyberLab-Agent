"""
ProjectMetadata — v6.0.0.A
طبقة مركزية لقراءة MASTER_REF.yaml.
إضافة فقط — لا تعدل أي سلوك موجود.
"""
import os
import yaml

MASTER_REF_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "configs", "MASTER_REF.yaml"
)


class ProjectMetadata:

    def __init__(self):
        # Internal storage. Do not access directly outside ProjectMetadata.
        self._data = {}
        self.reload()

    def reload(self):
        """إعادة تحميل MASTER_REF.yaml من القرص."""
        path = os.path.abspath(MASTER_REF_PATH)
        with open(path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

    # ── Public API ──────────────────────────────────────────
    def get(self, key: str, default=None):
        """قراءة مفتاح من المستوى الأول."""
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        """التحقق من وجود مفتاح."""
        return key in self._data

    def as_dict(self) -> dict:
        """نسخة كاملة من البيانات — للقراءة فقط."""
        return dict(self._data)

    def get_version(self) -> str:
        return self._data.get("project", {}).get("version", "unknown")

    def get_project_name(self) -> str:
        return self._data.get("project", {}).get("name", "unknown")

    def get_reference_version(self) -> str:
        return self._data.get("project", {}).get("reference_version", "unknown")

    def get_current_phase(self) -> dict:
        phase_id = self._data.get("current_phase", None)
        phases   = self._data.get("phases", [])
        for p in phases:
            if p.get("id") == phase_id:
                return p
        return {}

    def get_next_phase(self) -> dict:
        next_id = self._data.get("next_phase", None)
        phases  = self._data.get("phases", [])
        for p in phases:
            if p.get("id") == next_id:
                return p
        return {}

    def get_architecture_status(self) -> str:
        return self._data.get("project", {}).get("architecture_status", "unknown")
