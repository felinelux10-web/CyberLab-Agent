"""
Series 7 — Workflow Manager

المسؤولية:
- إدارة دورة حياة المهمة كاملاً.
"""

from .workflow_task      import WorkflowTask
from .workflow_context   import WorkflowContext
from .workflow_queue     import WorkflowQueue
from .workflow_scheduler import WorkflowScheduler
from .workflow_executor  import WorkflowExecutor
from .workflow_recovery  import WorkflowRecovery
from .workflow_resume    import WorkflowResume
from .workflow_pause     import WorkflowPause
from .workflow_cancel    import WorkflowCancel
from .workflow_logger    import WorkflowLogger
from .workflow_report    import WorkflowReport
from .workflow_state     import WorkflowState


class WorkflowManager:

    def __init__(self):
        self.queue     = WorkflowQueue()
        self.scheduler = WorkflowScheduler()
        self.executor  = WorkflowExecutor()
        self.recovery  = WorkflowRecovery()
        self.resume    = WorkflowResume()
        self.pause     = WorkflowPause()
        self.cancel    = WorkflowCancel()
        self.state     = WorkflowState()
        self.logger    = WorkflowLogger()

    def submit(self, name, steps, priority="normal"):
        task = WorkflowTask().create(name, steps, priority)
        self.queue.enqueue(task)
        self.logger.log("task_submitted", {"task_id": task["id"]})
        return task

    def run_next(self):
        result = self.scheduler.next_task(self.queue)
        if result["status"] == "empty":
            return {"status": "empty"}
        task    = result["task"]
        context = WorkflowContext().create(task)
        self.logger.log("task_started", {"task_id": task["id"]})
        while True:
            step_result = self.scheduler.next_step(context)
            if step_result["status"] == "finished":
                context["state"] = "completed"
                self.logger.log("task_completed", {"task_id": task["id"]})
                break
            step = step_result["step"]
            self.executor.execute_step(context, step)
            self.executor.complete_step(context, step)
            self.logger.log("step_completed", {"step": step.get("name")})
        return WorkflowReport().build(context, self.logger)
