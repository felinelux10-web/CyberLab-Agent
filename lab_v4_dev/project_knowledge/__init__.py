"""
P09 — Canonical Project Knowledge subsystem.

Single ownership boundary for project understanding.

Pipeline:
    Scanner -> Inventory -> Analyzer -> Knowledge Store
    -> Relationships -> Query

Legacy awareness/project_registry components are compatibility
surfaces only and must not become independent knowledge stores.
"""
from .core import ProjectKnowledgeCore

__all__ = ["ProjectKnowledgeCore"]
