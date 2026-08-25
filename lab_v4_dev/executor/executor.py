from __future__ import annotations

from lab_v4_dev.executor.contracts import (
    ExecutionContext,
    ExecutionRequest,
    ExecutionResult,
)
from lab_v4_dev.executor.throttle import check_resources
from lab_v4_dev.executor.shell_runner import run_shell
from lab_v4_dev.recovery.safe_apply import safe_apply
from lab_v4_dev.core.config import HARD_LIMITS


class Executor:
    """
    P011 canonical execution boundary.

    Responsibilities:
    - accept a validated ExecutionRequest;
    - enforce execution/resource limits;
    - dispatch the requested execution primitive;
    - return ExecutionResult.

    The Executor does NOT:
    - interpret user intent;
    - create plans;
    - assess planning risk;
    - make planning decisions;
    - perform recovery policy decisions.
    """

    def __init__(self, state, db, session=None):
        self.state = state
        self.db = db
        self.session = session
        self.commands_run = 0

    def _check_limits(self) -> dict:
        if not self.state.can_execute():
            return {
                "ok": False,
                "reason": f"agent in {self.state.mode} mode",
            }

        if self.commands_run >= HARD_LIMITS["max_shell_commands_per_task"]:
            return {
                "ok": False,
                "reason": "shell commands limit reached",
            }

        res = check_resources()
        if not res["ok"]:
            return {
                "ok": False,
                "reason": f"resources high — RAM:{res['ram_mb']}MB",
            }

        return {"ok": True}

    def _context_for(self, request: ExecutionRequest) -> ExecutionContext:
        return ExecutionContext(
            plan_id=request.plan_id,
            step_id=request.step_id,
            metadata=dict(request.metadata),
        )

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """
        Canonical P011 entry point.

        A Plan/PlanStep from P010 is translated into ExecutionRequest
        before reaching this method. The Executor performs execution only.
        """
        if not isinstance(request, ExecutionRequest):
            raise TypeError("execute() requires ExecutionRequest")

        context = self._context_for(request)

        check = self._check_limits()
        if not check["ok"]:
            return ExecutionResult(
                status="blocked",
                plan_id=context.plan_id,
                step_id=context.step_id,
                action=request.action,
                error=check["reason"],
                metadata={"execution_schema": "p11.v1"},
            )

        action = request.action

        if action in {"run_command", "shell", "command"}:
            return self._execute_command(request, context)

        if action in {"write_file", "edit_file"}:
            return self._execute_write_file(request, context)

        return ExecutionResult(
            status="unsupported",
            plan_id=context.plan_id,
            step_id=context.step_id,
            action=action,
            error=f"unsupported execution action: {action}",
            metadata={"execution_schema": "p11.v1"},
        )

    def _execute_command(
        self,
        request: ExecutionRequest,
        context: ExecutionContext,
    ) -> ExecutionResult:
        command = request.parameters.get("command")

        if not isinstance(command, str) or not command:
            return ExecutionResult(
                status="failed",
                plan_id=context.plan_id,
                step_id=context.step_id,
                action=request.action,
                error="missing parameters.command",
                metadata={"execution_schema": "p11.v1"},
            )

        self.commands_run += 1
        result = run_shell(command)

        if result.get("status") == "timeout":
            self.state.record_failure()
        elif result.get("status") == "ok":
            self.state.record_success()
        elif result.get("status") == "failed":
            self.state.record_failure()

        return ExecutionResult(
            status=self._normalize_status(result.get("status")),
            plan_id=context.plan_id,
            step_id=context.step_id,
            action=request.action,
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            exit_code=result.get("code"),
            error=result.get("stderr") if result.get("status") != "ok" else None,
            metadata={
                "execution_schema": "p11.v1",
                **dict(request.metadata),
            },
        )

    def _execute_write_file(
        self,
        request: ExecutionRequest,
        context: ExecutionContext,
    ) -> ExecutionResult:
        if not self.state.can_edit_files():
            return ExecutionResult(
                status="blocked",
                plan_id=context.plan_id,
                step_id=context.step_id,
                action=request.action,
                error=f"agent in {self.state.mode} mode",
                metadata={"execution_schema": "p11.v1"},
            )

        file_path = request.parameters.get("file_path")
        content = request.parameters.get("content")

        if not isinstance(file_path, str) or not file_path:
            return ExecutionResult(
                status="failed",
                plan_id=context.plan_id,
                step_id=context.step_id,
                action=request.action,
                error="missing parameters.file_path",
                metadata={"execution_schema": "p11.v1"},
            )

        if not isinstance(content, str):
            return ExecutionResult(
                status="failed",
                plan_id=context.plan_id,
                step_id=context.step_id,
                action=request.action,
                error="parameters.content must be a string",
                metadata={"execution_schema": "p11.v1"},
            )

        result = safe_apply(file_path, content)

        if result.get("status") == "ok":
            self.state.record_success()
            if self.session:
                self.session.record_file_modified()
        else:
            self.state.record_failure()

        return ExecutionResult(
            status=self._normalize_status(result.get("status")),
            plan_id=context.plan_id,
            step_id=context.step_id,
            action=request.action,
            target=file_path,
            error=result.get("reason") if result.get("status") != "ok" else None,
            metadata={
                "execution_schema": "p11.v1",
                **dict(request.metadata),
                "snapshot": result.get("snapshot"),
            },
        )

    @staticmethod
    def _normalize_status(status: str | None) -> str:
        if status == "ok":
            return "success"
        if status in {"blocked", "failed", "timeout", "unsupported"}:
            return status
        return status or "failed"

    # ------------------------------------------------------------------
    # Legacy compatibility wrappers
    # ------------------------------------------------------------------

    def run_command(self, command: str) -> dict:
        """
        Legacy wrapper.

        New callers must use execute(ExecutionRequest).
        """
        request = ExecutionRequest(
            plan_id="legacy",
            step_id=f"legacy-command-{self.commands_run + 1}",
            action="run_command",
            parameters={"command": command},
            metadata={"legacy_wrapper": True},
        )
        return self.execute(request).to_dict()

    def write_file(self, file_path: str, content: str) -> dict:
        """
        Legacy wrapper.

        New callers must use execute(ExecutionRequest).
        """
        request = ExecutionRequest(
            plan_id="legacy",
            step_id=f"legacy-write-{self.commands_run + 1}",
            action="write_file",
            parameters={
                "file_path": file_path,
                "content": content,
            },
            metadata={"legacy_wrapper": True},
        )
        return self.execute(request).to_dict()

    def reset_counters(self):
        self.commands_run = 0
