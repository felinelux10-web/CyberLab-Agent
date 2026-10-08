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
        data.setdefault("records", {})
        return data

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = f"{self.path}.{secrets.token_hex(4)}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, self.path)

    def _authorize(self, access: PersonalMemoryAccess) -> bool:
        allowed = access.permission == "allowed" and access.scope in _ALLOWED.get(access.requester, set())
        self._audit.append({
            "requester": access.requester, "purpose": access.purpose,
            "scope": access.scope, "allowed": allowed, "at": _now(),
        })
        return allowed

    def remember(self, key: str, value: str, *, category: str, source: str = "explicit_user_command", confidence: str = "EXPLICIT", access: PersonalMemoryAccess) -> bool:
        if access.requester != "explicit_user_command" or not self._authorize(access):
            return False
        data = self._load()
        data["records"][key] = {
            "memory_id": f"pm:{secrets.token_hex(8)}", "key": key, "value": value,
            "category": category, "confidence": confidence, "source": source,
            "created_at": data.get("records", {}).get(key, {}).get("created_at", _now()),
            "updated_at": _now(), "status": "ACTIVE",
        }
        self._save(data)
        return True

    def get_preferences(self, *, category: str, access: PersonalMemoryAccess) -> dict:
        if access.scope != category or not self._authorize(access):
            return {}
        data = self._load()
        return {
            record["key"]: record["value"]
            for record in data.get("records", {}).values()
            if record.get("category") == category and record.get("status") == "ACTIVE"
        }

    def forget(self, key: str, *, access: PersonalMemoryAccess) -> bool:
        if access.requester != "explicit_user_command" or not self._authorize(access):
            return False
        data = self._load()
        existed = key in data.get("records", {})
        if existed:
            del data["records"][key]
            self._save(data)
        return existed

    def audit_events(self) -> list[dict]:
        return list(self._audit)


def get_personal_preferences(*, category: str, purpose: str, requester: str) -> dict:
    """Least-privilege helper; intentionally no full-dump API."""
    access = PersonalMemoryAccess(requester=requester, purpose=purpose, scope=category)
    return PersonalMemoryStore().get_preferences(category=category, access=access)


__all__ = ["PersonalMemoryAccess", "PersonalMemoryStore", "get_personal_preferences"]
