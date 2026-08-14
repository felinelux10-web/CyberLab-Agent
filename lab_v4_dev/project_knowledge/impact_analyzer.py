"""
PIE-003A — Impact Analyzer

المسؤولية:
- تحليل الملفات المتأثرة.
- تتبع الاعتماديات بشكل تكراري باستخدام BFS.
"""

import os
from collections import deque

from .graph_query import get_importers


class ChangeImpactAnalyzer:

    def analyze_file_change(self, file_path):

        visited = set()
        result = []

        queue = deque([file_path])

        while queue:

            current = queue.popleft()

            dependents = get_importers(current)

            if not dependents and "." in current:
                dependents = get_importers(
                    os.path.splitext(current)[0]
                )

            for item in dependents:

                if item in visited:
                    continue

                visited.add(item)
                result.append(item)

                queue.append(item)

        return result


    def _collect_impact(self, target, impacted):
        """
        Deprecated.
        بقيت فقط للتوافق مع الإصدارات القديمة.
        """
        return
