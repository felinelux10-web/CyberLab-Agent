"""
PIE-003B — Impact Classifier
"""

class ImpactClassifier:

    def classify(self, impacted):

        classified = []

        for index, file in enumerate(impacted):

            if index == 0:
                level = "direct"
            else:
                level = "indirect"

            classified.append(
                {
                    "file": file,
                    "level": level,
                    "reason": "depends on changed component",
                }
            )

        return classified
