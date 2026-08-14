"""
PIE-006B — Execution Validator

المسؤولية:
- التحقق من صحة خطة التنفيذ.
"""


class ExecutionValidator:

    REQUIRED = (
        "file",
        "priority",
        "action",
    )

    def validate(self, execution_sequence):

        seen = set()
        errors = []

        for item in execution_sequence:

            for field in self.REQUIRED:

                if field not in item:
                    errors.append(
                        f"missing:{field}"
                    )

            file = item.get("file")

            if file in seen:
                errors.append(
                    f"duplicate:{file}"
                )

            seen.add(file)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }
