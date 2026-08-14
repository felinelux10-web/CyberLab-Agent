# CyberLab Agent v4.0
# executor/executor.py

from lab_v4_dev.executor.throttle import check_resources
from lab_v4_dev.executor.shell_runner import run_shell
from lab_v4_dev.recovery.safe_apply import safe_apply
from lab_v4_dev.core.config import HARD_LIMITS

class Executor:

    def __init__(self, state, db, session=None):
        self.state = state
        self.db = db
        self.session = session
        self.commands_run = 0

    def _check_limits(self) -> dict:
        if not self.state.can_execute():
            return {"ok": False, "reason": f"agent in {self.state.mode} mode"}

        if self.commands_run >= HARD_LIMITS["max_shell_commands_per_task"]:
            return {"ok": False, "reason": "shell commands limit reached"}

        res = check_resources()
        if not res["ok"]:
            return {"ok": False, "reason": f"resources high — RAM:{res['ram_mb']}MB"}

        return {"ok": True}

    def run_command(self, command: str) -> dict:
        check = self._check_limits()
        if not check["ok"]:
            return {"status": "blocked", "reason": check["reason"]}

        self.commands_run += 1
        result = run_shell(command)

        if result["status"] == "timeout":
            self.state.record_failure()
        else:
            self.state.record_success()

        return result

    def write_file(self, file_path: str, content: str) -> dict:
        if not self.state.can_edit_files():
            return {"status": "blocked", "reason": f"agent in {self.state.mode} mode"}

        check = self._check_limits()
        if not check["ok"]:
            return {"status": "blocked", "reason": check["reason"]}

        result = safe_apply(file_path, content)

        if result["status"] != "ok":
            self.state.record_failure()
        else:
            self.state.record_success()
            if self.session:
                self.session.record_file_modified()

        return result

    def reset_counters(self):
        self.commands_run = 0
