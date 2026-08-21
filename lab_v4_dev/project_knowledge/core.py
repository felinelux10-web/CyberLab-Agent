"""
P09 — Canonical Project Knowledge Core.

Single ownership boundary for project understanding.

The core coordinates the existing project-knowledge components through
their real APIs. It does not duplicate scanner, analyzer, persistence,
relationship, or query algorithms.
"""

from __future__ import annotations

from typing import Any


class ProjectKnowledgeCore:
    DOMAIN = "project_knowledge"
    VERSION = "P09"

    def __init__(
        self,
        *,
        scanner=None,
        analyzer_registry=None,
        analysis_engine=None,
        knowledge_store=None,
        relationship_engine=None,
        query_engine=None,
        graph_query=None,
    ):
        self.scanner = scanner
        self.analyzer_registry = analyzer_registry
        self.analysis_engine = analysis_engine
        self.knowledge_store = knowledge_store
        self.relationship_engine = relationship_engine
        self.query_engine = query_engine
        self.graph_query = graph_query

    # ----------------------------------------------------------
    # Scanner boundary
    # ----------------------------------------------------------

    def scan(self, project_root):
        if self.scanner is None:
            raise RuntimeError(
                "ProjectKnowledgeCore scanner is not configured"
            )

        if hasattr(self.scanner, "scan"):
            return self.scanner.scan(project_root)

        if callable(self.scanner):
            return self.scanner(project_root)

        raise TypeError("Configured scanner has no supported scan API")

    # ----------------------------------------------------------
    # Analyzer boundary
    # ----------------------------------------------------------

    def analyze(self, file_path):
        if self.analysis_engine is None:
            raise RuntimeError(
                "ProjectKnowledgeCore analysis_engine is not configured"
            )

        if hasattr(self.analysis_engine, "analyze_file"):
            return self.analysis_engine.analyze_file(file_path)

        if callable(self.analysis_engine):
            return self.analysis_engine(file_path)

        raise TypeError(
            "Configured analysis_engine has no supported analyze API"
        )

    # ----------------------------------------------------------
    # Canonical analysis pipeline
    # ----------------------------------------------------------

    def analyze_file(
        self,
        file_path,
        *,
        file_hash="",
        size=0,
        modified="",
        persist=True,
    ):
        """
        Canonical single-file knowledge pipeline.

        Flow:
            AnalysisEngine
                -> RelationshipEngine
                -> KnowledgeStore

        AnalysisEngine itself remains persistence-free.
        """
        result = self.analyze(file_path)

        relationships = self.relationships(result)

        if persist:
            self.store(
                result,
                file_hash=file_hash,
                size=size,
                modified=modified,
            )

            if relationships:
                self._save_relationships(relationships)

        return {
            "result": result,
            "relationships": tuple(relationships),
            "persisted": bool(persist),
        }

    # ----------------------------------------------------------
    # Relationship persistence boundary
    # ----------------------------------------------------------

    def _save_relationships(self, relationships):
        if self.knowledge_store is None:
            raise RuntimeError(
                "ProjectKnowledgeCore knowledge_store is not configured"
            )

        if hasattr(self.knowledge_store, "save_relationships"):
            return self.knowledge_store.save_relationships(
                relationships
            )

        if hasattr(self.knowledge_store, "save_relationship"):
            for relationship in relationships:
                self.knowledge_store.save_relationship(
                    relationship
                )
            return None

        raise TypeError(
            "Configured knowledge_store has no supported "
            "relationship persistence API"
        )

    # ----------------------------------------------------------
    # Persistence boundary
    # ----------------------------------------------------------

    def store(self, result, **metadata):
        if self.knowledge_store is None:
            raise RuntimeError(
                "ProjectKnowledgeCore knowledge_store is not configured"
            )

        if hasattr(self.knowledge_store, "store_analysis"):
            return self.knowledge_store.store_analysis(
                result,
                metadata.get("file_hash", ""),
                metadata.get("size", 0),
                metadata.get("modified", ""),
            )

        if callable(self.knowledge_store):
            return self.knowledge_store(result, **metadata)

        raise TypeError(
            "Configured knowledge_store has no supported store API"
        )

    # ----------------------------------------------------------
    # Relationship boundary
    # ----------------------------------------------------------

    def relationships(self, analysis_result):
        if self.relationship_engine is None:
            raise RuntimeError(
                "ProjectKnowledgeCore relationship_engine is not configured"
            )

        if hasattr(self.relationship_engine, "build"):
            return self.relationship_engine.build(analysis_result)

        if callable(self.relationship_engine):
            return self.relationship_engine(analysis_result)

        raise TypeError(
            "Configured relationship_engine has no supported build API"
        )

    # ----------------------------------------------------------
    # Query boundary
    # ----------------------------------------------------------

    def query(self, query):
        if self.query_engine is None:
            raise RuntimeError(
                "ProjectKnowledgeCore query_engine is not configured"
            )

        if hasattr(self.query_engine, "query"):
            return self.query_engine.query(query)

        if callable(self.query_engine):
            return self.query_engine(query)

        raise TypeError(
            "Configured query_engine has no generic query API"
        )

    # ----------------------------------------------------------
    # Graph query boundary
    # ----------------------------------------------------------

    def neighbors(self, target):
        if self.graph_query is None:
            raise RuntimeError(
                "ProjectKnowledgeCore graph_query is not configured"
            )

        if hasattr(self.graph_query, "get_neighbors"):
            return self.graph_query.get_neighbors(target)

        if callable(self.graph_query):
            return self.graph_query(target)

        raise TypeError(
            "Configured graph_query has no supported neighbor API"
        )

    # ----------------------------------------------------------
    # Capability declaration
    # ----------------------------------------------------------

    def capabilities(self) -> dict[str, bool]:
        return {
            "scanner": self.scanner is not None,
            "analyzer_registry": self.analyzer_registry is not None,
            "analysis_engine": self.analysis_engine is not None,
            "knowledge_store": self.knowledge_store is not None,
            "relationship_engine": self.relationship_engine is not None,
            "query_engine": self.query_engine is not None,
            "graph_query": self.graph_query is not None,
        }
