# CyberLab Agent v4.0
# intent/decomposer.py

from lab_v4_dev.planner.step_builder import shell_step, write_step, read_step

def decompose(parsed: dict) -> dict:
    action = parsed.get("action")
    target = parsed.get("target", "")
    content = parsed.get("content", "")

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
            "reason": f"cannot decompose action: {action}",
            "steps" : [],
        }

    return {
        "ok"    : True,
        "action": action,
        "target": target,
        "steps" : steps,
        "count" : len(steps),
    }
