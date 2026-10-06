"""Explicit compatibility inventory for legacy runtime paths.

This is classification metadata, not a second runtime router. The active
runtime remains ``run.py -> lab_v4_dev.core.agent``. Legacy modules stay in
the tree for compatibility until their callers and migration are proven.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyPath:
    path: str
    status: str
    callers: tuple[str, ...]
    replacement: str
    notes: str


CANONICAL_ENTRYPOINT = "run.py -> lab_v4_dev.core.agent.Agent"

LEGACY_PATHS = (
    LegacyPath(
        path="lab_v4/",
        status="legacy_compatibility",
        callers=(),
        replacement="lab_v4_dev/",
        notes="Kept for compatibility; no runtime imports were found in the active tree.",
    ),
    LegacyPath(
        path="lab_v4/llm/groq_client.py",
        status="legacy_direct_provider",
        callers=(),
        replacement="lab_v4_dev/llm/gateway.py",
        notes="Must not bypass the canonical gateway/privacy boundary.",
    ),
    LegacyPath(
        path="lab_v4/llm/smart_router.py",
        status="legacy_router",
        callers=(),
        replacement="lab_v4_dev/llm/gateway.py",
        notes="Retained until compatibility callers are explicitly migrated.",
    ),
)


def classify(path: str) -> LegacyPath | None:
    normalized = str(path).replace("\\", "/")
    for item in sorted(LEGACY_PATHS, key=lambda value: len(value.path), reverse=True):
        if normalized == item.path or normalized.startswith(item.path.rstrip("/") + "/"):
            return item
    return None


def active_runtime_entrypoint() -> str:
    return CANONICAL_ENTRYPOINT
