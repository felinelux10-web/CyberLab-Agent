from __future__ import annotations

import os

from lab_v4_dev.planner.decision_contracts import ImpactAssessment
from lab_v4_dev.project_knowledge.graph_query import get_importers


class ImpactAnalyzer:
    """
    Declarative impact analysis.

    Determines which project components are affected by a target.
    It performs no planning execution, permission checks, mutation,
    snapshotting, or recovery.
    """

    def analyze(self, file_path: str) -> ImpactAssessment:
        if not isinstance(file_path, str):
            raise TypeError("file_path must be a string")

        if not file_path:
            raise ValueError("file_path must not be empty")

        affected: list[str] = []
        visited: set[str] = set()
        queue: list[str] = [file_path]

        while queue:
            current = queue.pop(0)

            dependents = get_importers(current)

            if not dependents and "." in current:
                dependents = get_importers(
                    os.path.splitext(current)[0]
                )

            for item in dependents:
                if item in visited or item == file_path:
                    continue

                visited.add(item)
                affected.append(item)
                queue.append(item)

        level = "direct" if affected else "unknown"

        return ImpactAssessment(
            target=file_path,
            affected=tuple(affected),
            level=level,
            reason="dependency impact analysis",
        )


def analyze_impact(file_path: str) -> dict:
    """
    Compatibility wrapper for legacy callers.

    New P10 code should consume ImpactAssessment through ImpactAnalyzer.
    """
    return ImpactAnalyzer().analyze(file_path).to_dict()


__all__ = ["ImpactAnalyzer", "analyze_impact"]
