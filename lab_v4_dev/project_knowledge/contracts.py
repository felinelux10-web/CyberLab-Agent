"""
P09 — Project Knowledge contracts.

The contract deliberately contains project-understanding data only.
Runtime state, dialogue state, personal memory, planning and execution
state remain outside this layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProjectFile:
    path: str
    language: str | None = None
    analyzer: str | None = None
    size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectSymbol:
    name: str
    kind: str
    path: str
    line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectRelationship:
    source: str
    relation: str
    target: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeQuery:
    text: str
    path: str | None = None
    symbol: str | None = None
    relation: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class KnowledgeResult:
    items: tuple[Any, ...] = ()
    source: str = "project_knowledge"
    query: KnowledgeQuery | None = None
