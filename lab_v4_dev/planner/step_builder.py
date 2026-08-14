# CyberLab Agent v4.0
# planner/step_builder.py

def build_step(action: str, **kwargs) -> dict:
    step = {"action": action}
    step.update(kwargs)
    return step

def shell_step(command: str) -> dict:
    return build_step("shell", command=command)

def write_step(file_path: str, content: str) -> dict:
    return build_step("write_file", file=file_path, content=content)

def read_step(file_path: str) -> dict:
    return build_step("read_file", file=file_path)

def validate_steps(steps: list) -> dict:
    if not steps:
        return {"ok": False, "reason": "empty steps"}

    valid_actions = ["shell", "write_file", "read_file"]

    for i, step in enumerate(steps):
        if "action" not in step:
            return {"ok": False, "reason": f"step {i} missing action"}
        if step["action"] not in valid_actions:
            return {"ok": False, "reason": f"step {i} unknown action: {step['action']}"}

    return {"ok": True, "count": len(steps)}
