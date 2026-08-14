# CyberLab Agent v4.0
# planner/planner.py

from lab_v4.planner.step_builder import shell_step, write_step, read_step, validate_steps
from lab_v4.planner.validator import validate_plan
from lab_v4.memory.lessons import Lessons

class Planner:

    def __init__(self, db):
        self.db = db
        self.lessons = Lessons(db)

    def build(self, intent: dict) -> dict:
        action = intent.get("action")
        target = intent.get("target", "")
        content = intent.get("content", "")

        steps = []

        if action == "shell":
            steps = [shell_step(target)]

        elif action == "write_file":
            steps = [write_step(target, content)]

        elif action == "read_file":
            steps = [read_step(target)]

        elif action == "create_and_run":
            steps = [
                write_step(target, content),
                shell_step(f"python3 {target}"),
            ]

        else:
            return {
                "ok"    : False,
                "reason": f"unknown action: {action}",
            }

        plan = {"intent": intent, "steps": steps}
        validation = validate_plan(plan)

        if not validation["ok"]:
            return {
                "ok"    : False,
                "reason": validation["errors"],
            }

        return {
            "ok"   : True,
            "plan" : plan,
            "steps": steps,
            "count": len(steps),
        }

    def check_known_error(self, error: str) -> dict | None:
        lesson = self.lessons.find(error)
        if lesson and lesson["total_count"] > 0:
            return {
                "known"    : True,
                "solution" : lesson["solution"],
                "rate"     : lesson["success_count"] / lesson["total_count"],
            }
        return None
