# CyberLab Agent v4.0
# loop/event_loop.py

from lab_v4_dev.intent.parser import parse
from lab_v4_dev.intent.clarifier import clarify
from lab_v4_dev.intent.decomposer import decompose
from lab_v4_dev.planner.planner import Planner
from lab_v4_dev.monitor.health_check import check_health
from lab_v4_dev.monitor.budget import Budget
from lab_v4_dev.executor.executor import Executor
from lab_v4_dev.executor.plan_adapter import PlanExecutionAdapter
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
        self.plan_adapter = PlanExecutionAdapter()
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

        # 7. P10 -> P11 contract boundary
        #
        # P10 remains declarative. The adapter translates each approved
        # PlanStep into the canonical P11 ExecutionRequest.
        # Execution itself remains exclusively inside Executor.
        task_id = (
            self.history.add(user_input)
            if self.history is not None
            else None
        )

        requests = []

        try:
            for step in plan.steps:
                requests.append(
                    self.plan_adapter.to_request(plan, step)
                )
        except Exception as e:
            return {
                "status": "failed",
                "task_id": task_id,
                "plan": plan.to_dict(),
                "reason": str(e),
            }

        results = []

        for request in requests:
            result = self.executor.execute(request)
            results.append(result.to_dict())

        return {
            "status": "executed",
            "task_id": task_id,
            "plan": plan.to_dict(),
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
