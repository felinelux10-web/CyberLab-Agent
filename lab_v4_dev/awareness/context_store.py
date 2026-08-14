# CyberLab Agent v4.0
# awareness/context_store.py

from lab_v4_dev.memory.db import Database
from lab_v4_dev.awareness.scanner import scan_file, scan_directory
from lab_v4_dev.awareness.model_builder import build_model, get_file_context
from lab_v4_dev.core.project_context import get_active_project_root

class ContextStore:

    def __init__(self, db: Database):
        self.db = db
        self._model = None

    def get_file(self, path: str) -> dict | None:
        return get_file_context(path, self.db)

    def refresh_file(self, path: str) -> dict:
        return scan_file(path, self.db)

    def refresh_directory(self, directory: str | None = None) -> dict:
        if directory is None:
            directory = get_active_project_root()
        return scan_directory(directory, self.db)

    def get_model(self, force: bool = False) -> dict:
        if self._model is None or force:
            self._model = build_model(self.db)
        return self._model

    def invalidate(self):
        self._model = None

    def file_changed(self, path: str) -> bool:
        import hashlib
        stored = self.get_file(path)
        if not stored:
            return True
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                h.update(f.read())
            return h.hexdigest() != stored["file_hash"]
        except Exception:
            return True

    def summary(self) -> dict:
        model = self.get_model()
        return {
            "total_files"  : model["total_files"],
            "python_files" : len(model["python_files"]),
            "config_files" : len(model["config_files"]),
        }
