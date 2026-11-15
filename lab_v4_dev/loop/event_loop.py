# CyberLab Agent v4.0
# loop/event_loop.py

from lab_v4_dev.planner.planner import Planner
from lab_v4_dev.monitor.health_check import check_health
from lab_v4_dev.monitor.budget import Budget
from lab_v4_dev.executor.executor import Executor
from lab_v4_dev.executor.plan_adapter import PlanExecutionAdapter
from lab_v4_dev.loop.idle_manager import IdleManager
from lab_v4_dev.loop.scheduler import Scheduler
from lab_v4_dev.core.contracts import PreparedExecutionRequest

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

    def submit_prepared(self, request: PreparedExecutionRequest):
        """Queue an already-resolved execution request.

        This path deliberately does not accept raw conversation text and
        never invokes the legacy parser/clarifier/decomposer pipeline.
        """
        if not isinstance(request, PreparedExecutionRequest):
            raise TypeError("submit_prepared requires PreparedExecutionRequest")
        decision = request.route_decision
        if decision.route != "L-EXEC" or decision.evidence_scope != "work_state":
            raise PermissionError("prepared execution requires L-EXEC work_state authorization")

        self.scheduler.add({"prepared": request})

    def _process_prepared(self, request: PreparedExecutionRequest) -> dict:
        """Process a prepared orchestration handoff without re-parsing input."""
        decision = request.route_decision
        if decision.route != "L-EXEC" or decision.evidence_scope != "work_state":
            return {
                "status": "denied",
                "reason": "prepared execution route authorization is invalid",
                "executed": False,
            }

        execution_metadata = request.metadata.get("execution", {})
        health_check_enabled = execution_metadata.get("health_check", True)

        if health_check_enabled:
            health = check_health(self.state)
            if not health["healthy"]:
                return {"status": "blocked", "reason": "system unhealthy"}

        budget_check = self.budget.can_run_task()
        if not budget_check["ok"]:
            return {"status": "blocked", "reason": budget_check["reason"]}

        execution = request.metadata.get("execution")
        if not isinstance(execution, dict):
            return {
                "status": "failed",
                "reason": "prepared request missing execution specification",
            }

        action = execution.get("action")
        parameters = execution.get("parameters", {})

        if not action or not isinstance(parameters, dict):
            return {
                "status": "failed",
                "reason": "invalid execution specification",
            }

        actions = [{
            "step_id": "step-1",
            "action": action,
            "parameters": dict(parameters),
        }]

        try:
            plan = self.planner.from_actions(
                request.intent,
                actions,
                plan_id=request.request_id or "",
                metadata={
                    **dict(request.metadata),
                    "source": "event_loop.prepared",
                },
            )
        except Exception as e:
            return {"status": "failed", "reason": str(e)}

        requests = []

        try:
            for step in plan.steps:
                requests.append(
                    self.plan_adapter.to_request(plan, step)
                )
        except Exception as e:
            return {
                "status": "failed",
                "plan": plan.to_dict(),
                "reason": str(e),
            }

        results = []

        for execution_request in requests:
            result = self.executor.execute(execution_request)
            results.append(result.to_dict())

        return {
            "status": "executed",
            "plan": plan.to_dict(),
            "results": results,
        }

    def tick(self) -> dict | None:
        if not self.scheduler.has_tasks():
            self.idle.sleep()
            return None

        self.idle.reset()
        task = self.scheduler.next()
        prepared = task.get("prepared") if isinstance(task, dict) else None
        if not isinstance(prepared, PreparedExecutionRequest):
            return {
                "status": "denied",
                "source": "event_loop_prepared_request_required",
                "executed": False,
                "reason": "EventLoop accepts only RouteDecision-bound PreparedExecutionRequest objects.",
            }
        return self._process_prepared(prepared)

    def stop(self):
        self.running = False
