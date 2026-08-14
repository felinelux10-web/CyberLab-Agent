"""
PIE-001H — Analysis Engine

المسؤولية:
- اختيار المحلل المناسب حسب امتداد الملف.
- تشغيل عملية التحليل.
- إعادة AnalysisResult.

لا يقوم بـ:
- حفظ النتائج.
- تحديث قاعدة المعرفة.
- تحليل مشروع كامل.
"""

import os

from .analyzer_registry import get_registry
from .knowledge_store import store_analysis, save_relationships
from .relationship_engine import RelationshipEngine


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

        result = analyzer.analyze(file_path)

        relationships = RelationshipEngine().build(result)

        save_relationships(relationships)

        store_analysis(result)

        return result
