# CyberLab Agent v4.0
# planner/validator.py

from lab_v4.recovery.permissions import is_frozen
from lab_v4.core.config import HARD_LIMITS

def validate_plan(plan: dict) -> dict:
    errors = []

    # تحقق من وجود steps
    steps = plan.get("steps", [])
    if not steps:
        errors.append("plan has no steps")

    # تحقق من عدد الخطوات
    if len(steps) > HARD_LIMITS["max_shell_commands_per_task"]:
        errors.append(f"too many steps: {len(steps)}")

    # تحقق من كل خطوة
    for i, step in enumerate(steps):
        action = step.get("action")

        # خطوات الكتابة — تحقق من الصلاحيات
        if action == "write_file":
            file_path = step.get("file", "")
            if is_frozen(file_path):
                errors.append(f"step {i} targets frozen zone: {file_path}")

        # خطوات Shell — تحقق من الأوامر الخطيرة
        if action == "shell":
            command = step.get("command", "")
            dangerous = ["rm -rf", "mkfs", "dd if", "> /dev"]
            for d in dangerous:
                if d in command:
                    errors.append(f"step {i} dangerous command: {d}")

    if errors:
        return {"ok": False, "errors": errors}

    return {"ok": True, "steps_count": len(steps)}
