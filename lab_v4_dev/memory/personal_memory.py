"""Private personal memory boundary.

No component should read the backing file directly. Callers must use an
access request and receive only the requested category's minimal records.
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime

PERSONAL_MEMORY_PATH = os.path.expanduser("~/.cyberlab_agent/private/personal_memory.json")
_ALLOWED = {
    "response_personalization": {"communication", "learning"},
    "workflow_personalization": {"work_style", "projects"},
    "explicit_user_command": {"communication", "learning", "work_style", "projects", "personal"},
}


@dataclass(frozen=True)
class PersonalMemoryAccess:
    requester: str
    purpose: str
    scope: str
    permission: str = "allowed"


def _now() -> str:
    return datetime.now().isoformat()


class PersonalMemoryStore:
    def __init__(self, path: str | None = None):
        self.path = path or PERSONAL_MEMORY_PATH
        self._audit = []

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"schema_version": 1, "records": {}}
        with open(self.path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("personal memory must be a JSON object")
        data.setdefault("records", {})
        if not isinstance(data["records"], dict):
            raise ValueError("personal memory records must be an object")
        return data

    def _save(self, data: dict) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, mode=0o700, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass
        temporary = f"{self.path}.{secrets.token_hex(4)}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def _audit_event(self, access: PersonalMemoryAccess, operation: str, allowed: bool, success: bool) -> None:
        self._audit.append({
            "operation": operation,
            "requester": access.requester,
            "purpose": access.purpose,
            "scope": access.scope,
            "allowed": allowed,
            "success": success,
            "at": _now(),
        })

    def _authorize(self, access: PersonalMemoryAccess, operation: str = "access") -> bool:
        allowed = access.permission == "allowed" and access.scope in _ALLOWED.get(access.requester, set())
        self._audit_event(access, operation, allowed, False)
        return allowed

    def remember(self, key: str, value: str, *, category: str, source: str = "explicit_user_command", confidence: str = "EXPLICIT", access: PersonalMemoryAccess) -> bool:
        if (
            access.requester != "explicit_user_command"
            or category != access.scope
            or not self._authorize(access, "remember")
        ):
            return False
        try:
            data = self._load()
            data["records"][key] = {
                "memory_id": f"pm:{secrets.token_hex(8)}", "key": key, "value": value,
                "category": category, "confidence": confidence, "source": source,
                "created_at": data.get("records", {}).get(key, {}).get("created_at", _now()),
                "updated_at": _now(), "status": "ACTIVE",
            }
            self._save(data)
            self._audit[-1]["success"] = True
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def get_preferences(self, *, category: str, access: PersonalMemoryAccess) -> dict:
        if access.scope != category or not self._authorize(access, "read"):
            return {}
        try:
            data = self._load()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}
        return {
            record["key"]: record["value"]
            for record in data.get("records", {}).values()
            if isinstance(record, dict)
            and record.get("category") == category
            and record.get("status") == "ACTIVE"
        }

    def forget(self, key: str, *, access: PersonalMemoryAccess) -> bool:
        if access.requester != "explicit_user_command" or not self._authorize(access, "forget"):
            return False
        try:
            data = self._load()
            record = data.get("records", {}).get(key)
            if not record or record.get("category") != access.scope:
                return False
            del data["records"][key]
            self._save(data)
            self._audit[-1]["success"] = True
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def audit_events(self) -> list[dict]:
        return list(self._audit)


def get_personal_preferences(*, category: str, purpose: str, requester: str) -> dict:
    """Least-privilege helper; intentionally no full-dump API."""
    access = PersonalMemoryAccess(requester=requester, purpose=purpose, scope=category)
    return PersonalMemoryStore().get_preferences(category=category, access=access)


__all__ = ["PersonalMemoryAccess", "PersonalMemoryStore", "get_personal_preferences"]
