"""
PIE-003C — Impact Reasoner

المسؤولية:
- تفسير سبب التأثير.

لا يقوم بـ:
- تعديل الملفات.
- تحليل AST.
- تحديث قاعدة البيانات.
"""


class ImpactReasoner:

    def explain(self, changed_file, classified_results):

        explanations = []

        for item in classified_results:

            explanations.append(
                {
                    "file": item["file"],
                    "reason": (
                        f"{item['file']} depends on "
                        f"{changed_file}"
                    ),
                    "impact_type": "dependency_change",
                    "confidence": "high",
                }
            )

        return explanations
