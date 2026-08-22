# CyberLab Agent v4.0
# loop/event_loop.py

from lab_v4_dev.intent.parser import parse
from lab_v4_dev.intent.clarifier import clarify
from lab_v4_dev.intent.decomposer import decompose
from lab_v4_dev.planner.planner import Planner
from lab_v4_dev.monitor.health_check import check_health
from lab_v4_dev.monitor.budget import Budget
from lab_v4_dev.executor.executor import Executor
from lab_v4_dev.loop.idle_manager import IdleManager
from lab_v4_dev.loop.scheduler import Scheduler
from lab_v4_dev.core.config import HARD_LIMITS

class EventLoop:

    def __init__(self, state, db, session=None, memory=None):
        self.state     = state
        self.db        = db
        self.memory    = memory

        # P07 — canonical Memory ownership.
        # Legacy callers may still provide only session.
        if self.memory is None:
            self.memory = getattr(session, "memory", None)

        # P10 — Planner is declarative and has no runtime dependencies.
        self.planner   = Planner()
        self.executor  = Executor(state, db, session)
        self.budget    = Budget()
        self.history   = self.memory.tasks if self.memory is not None else None
        self.lessons   = self.memory.lessons if self.memory is not None else None
        self.idle      = IdleManager()
        self.scheduler = Scheduler()
        self.running   = False

    def submit(self, user_input: str):
        self.scheduler.add({"input": user_input})

    def _process(self, task: dict) -> dict:
        user_input = task.get("input", "")

        # 1. health check
        health = check_health(self.state)
        if not health["healthy"]:
            return {"status": "blocked", "reason": "system unhealthy"}

        # 2. budget check
        budget_check = self.budget.can_run_task()
        if not budget_check["ok"]:
            return {"status": "blocked", "reason": budget_check["reason"]}

        # 3. parse intent
        parsed = parse(user_input)

        # 4. clarify if needed
        if parsed.get("intent") not in ("unsupported", "unclear"):
            clarification = clarify(parsed)
            if clarification["needed"]:
                return {
                    "status"  : "needs_clarification",
                    "question": clarification["question"],
                }

        # 5. decompose
        decomposed = decompose(parsed)
        if not decomposed["ok"]:
            return {"status": "failed", "reason": decomposed["reason"]}

        # 6. build P10 declarative plan
        actions = []

        for index, step in enumerate(decomposed["steps"], start=1):
            action = step.get("action")
            parameters = {
                key: value
                for key, value in step.items()
                if key != "action"
            }

            actions.append({
                "step_id": f"step-{index}",
                "action": action,
                "parameters": parameters,
            })

        try:
            plan = self.planner.from_actions(
                parsed,
                actions,
                metadata={"source": "event_loop"},
            )
        except Exception as e:
            return {"status": "failed", "reason": str(e)}

        # 7. execute steps
        task_id = self.history.add(user_input) if self.history is not None else None
        results = []

        for step in plan.steps:
            action = step.action
            parameters = step.parameters

            if action == "shell":
                r = self.executor.run_command(parameters["command"])
            elif action == "write_file":
                r = self.executor.write_file(
                    parameters["file"],
                    parameters.get("content", ""),
                )
            elif action == "read_file":
                try:
                    content = open(parameters["file"]).read()
                    r = {"status": "ok", "output": content[:200]}
                except Exception as e:
                    r = {"status": "failed", "reason": str(e)}
            else:
                r = {"status": "skipped"}

            results.append(r)

            if r["status"] == "failed":
                self.budget.record_failure()
                self.state.record_failure()
                failures = self.state.consecutive_failures
                if failures >= HARD_LIMITS["max_consecutive_failures"]:
                    self.state.enter_safe_mode("max failures reached")
                break

        # 8. update history
        all_ok = all(r["status"] == "ok" for r in results)
        final_status = "done" if all_ok else "failed"
        if self.history is not None and task_id is not None:
            self.history.update_status(task_id, final_status)
        self.budget.record_task()

        if all_ok:
            self.budget.record_success()
            self.state.record_success()

        return {
            "status" : final_status,
            "task_id": task_id,
            "results": results,
        }

    def tick(self) -> dict | None:
        if not self.scheduler.has_tasks():
            self.idle.sleep()
            return None

        self.idle.reset()
        task = self.scheduler.next()
        return self._process(task)

    def stop(self):
        self.running = False
