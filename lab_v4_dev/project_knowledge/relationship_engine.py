"""
PIE-002B — Relationship Engine

المسؤولية:
- استخراج العلاقات من نتائج التحليل.
- بناء نموذج موحد للعلاقات.

لا يقوم بـ:
- الكتابة في قاعدة البيانات.
- تنفيذ استعلامات.
- تحليل AST مباشرة.
"""

from dataclasses import dataclass


@dataclass
class Relationship:
    source: str
    target: str
    relation_type: str
    target_kind: str


class RelationshipEngine:
    """
    يبني العلاقات العامة داخل المشروع.
    """

    def build(self, analysis_result):
        relationships = []

        for dep in analysis_result.dependencies:
            relationships.append(
                Relationship(
                    source=analysis_result.file_path,
                    target=dep["name"],
                    relation_type="imports",
                    target_kind=dep["kind"],
                )
            )

        return relationships
