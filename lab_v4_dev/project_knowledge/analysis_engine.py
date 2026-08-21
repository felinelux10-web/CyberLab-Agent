"""
P09 — Analysis Engine.

Responsibility:
    Select the appropriate analyzer and analyze one file.

The engine is deliberately PURE with respect to persistence:
    - no database writes
    - no relationship persistence
    - no knowledge-store access

Persistence and relationship coordination belong to
ProjectKnowledgeCore.
"""

from __future__ import annotations

import os

from .analyzer_registry import get_registry


class AnalysisEngine:

    def analyze_file(self, file_path: str):
        ext = os.path.splitext(file_path)[1].lower()

        registry = get_registry()

        language = registry.supports(ext)

        if language is None:
            raise ValueError(
                f"No analyzer for extension: {ext}"
            )

        info = registry.get(language)

        if info is None:
            raise RuntimeError(
                f"Analyzer not registered: {language}"
            )

        if info.analyzer_class is None:
            raise RuntimeError(
                f"Analyzer unavailable: {language}"
            )

        analyzer = info.analyzer_class()

        return analyzer.analyze(file_path)
