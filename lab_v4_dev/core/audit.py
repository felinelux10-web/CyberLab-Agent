# CyberLab Agent v4.0
# core/audit.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, Optional

from lab_v4_dev.core.logger import log

AUDIT_FILE = "execution_audit.json"


@dataclass
class EventRecord:
    timestamp: str
    event: str
    source: str
    context: Dict[str, Any]
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _move_corrupt(path: str):
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        corrupt_path = f"{path}.corrupt.{ts}"
        os.replace(path, corrupt_path)
        log.info("Moved corrupted audit file to %s", corrupt_path)
    except Exception:
        log.exception("Failed to move corrupted audit file %s", path)


def _load_audit_file(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            log.warning("Audit file %s contains unexpected JSON (not a list); preserving and starting fresh", path)
            # Move corrupt/unexpected file aside to avoid data loss
            try:
                _move_corrupt(path)
            except Exception:
                pass
            return []
    except Exception:
        # If file is corrupted or unreadable, preserve it and don't crash the caller.
        log.exception("Failed to read audit file %s", path)
        try:
            _move_corrupt(path)
        except Exception:
            pass
        return []


def _write_audit_file(path: str, entries: list) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        log.exception("Failed to write audit file %s", path)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def emit_event(event: str, source: str = "system", context: Optional[Dict[str, Any]] = None, details: Optional[Dict[str, Any]] = None, persist: bool = True) -> EventRecord:
    """
    Emit a canonical audit/event record.

    - Reuses the existing core logger for observability.
    - Appends a stable event record shape to execution_audit.json when persist is True.

    This function is intentionally small: it provides a single well-known path for
    producing structured events without replacing other specialized audit mechanisms.
    """
    context = context or {}
    details = details or {}

    # Use timezone-aware UTC timestamp
    ts = datetime.now(timezone.utc).isoformat()

    rec = EventRecord(
        timestamp=ts,
        event=event,
        source=source,
        context=dict(context),
        details=dict(details),
    )

    # Structured logging — reuse existing logger instead of creating a new system.
    try:
        log.info("EVENT %s | source=%s | details=%s", event, source, details)
    except Exception:
        # Logging should never raise to callers
        pass

    if persist:
        path = os.path.join(os.getcwd(), AUDIT_FILE)
        entries = _load_audit_file(path)
        entries.append(rec.to_dict())
        _write_audit_file(path, entries)

    return rec
