# CyberLab Agent v4.0
# core/audit.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, Optional

from lab_v4_dev.core.logger import log

CYBERLAB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AUDIT_FILE = os.path.join(CYBERLAB_ROOT, "execution_audit.json")
_DEFAULT_AUDIT_FILE = os.path.realpath(AUDIT_FILE)
_TEST_RUNTIME_ENV = "CYBERLAB_TEST_RUNTIME_DIR"


def _audit_path() -> str:
    """Use an isolated audit file during pytest without changing production defaults.

    Explicitly configured paths (including test monkeypatches) always take
    precedence over the test-runtime fallback.
    """
    runtime_dir = os.environ.get(_TEST_RUNTIME_ENV)
    if runtime_dir and os.path.realpath(AUDIT_FILE) == _DEFAULT_AUDIT_FILE:
        return os.path.join(runtime_dir, "execution_audit.json")
    return AUDIT_FILE


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
            try:
                _move_corrupt(path)
            except Exception:
                pass
            return []
    except Exception:
        log.exception("Failed to read audit file %s", path)
        try:
            _move_corrupt(path)
        except Exception:
            pass
        return []


def _write_audit_file(path: str, entries: list) -> None:
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or os.curdir, exist_ok=True)
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

    Structured events are persisted to the configured audit file during normal
    operation. Under pytest, the default destination is redirected to the
    temporary test runtime directory; explicit destinations remain respected.
    """
    context = context or {}
    details = details or {}
    ts = datetime.now(timezone.utc).isoformat()

    rec = EventRecord(
        timestamp=ts,
        event=event,
        source=source,
        context=dict(context),
        details=dict(details),
    )

    try:
        log.info("EVENT %s | source=%s | details=%s", event, source, details)
    except Exception:
        pass

    if persist:
        path = _audit_path()
        entries = _load_audit_file(path)
        entries.append(rec.to_dict())
        _write_audit_file(path, entries)

    return rec
