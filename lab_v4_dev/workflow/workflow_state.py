"""P013 canonical workflow task state machine."""


class WorkflowState:
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"

    ALL = frozenset({
        PENDING,
        RUNNING,
        PAUSED,
        CANCELLED,
        FAILED,
        COMPLETED,
    })

    TERMINAL = frozenset({
        COMPLETED,
        CANCELLED,
    })

    TRANSITIONS = {
        PENDING: frozenset({
            RUNNING,
            CANCELLED,
        }),
        RUNNING: frozenset({
            PAUSED,
            FAILED,
            COMPLETED,
            CANCELLED,
        }),
        PAUSED: frozenset({
            RUNNING,
            CANCELLED,
        }),
        FAILED: frozenset({
            RUNNING,
            CANCELLED,
        }),
        COMPLETED: frozenset(),
        CANCELLED: frozenset(),
    }

    def validate(self, state: str) -> bool:
        return state in self.ALL

    def can_transition(self, current: str, target: str) -> bool:
        return (
            self.validate(current)
            and self.validate(target)
            and target in self.TRANSITIONS.get(current, frozenset())
        )

    def transition(self, current: str, target: str) -> dict:
        if not self.can_transition(current, target):
            return {
                "status": "error",
                "state": current,
                "reason": f"cannot transition from {current} to {target}",
            }

        return {
            "status": "ok",
            "state": target,
        }

    def is_terminal(self, state: str) -> bool:
        return state in self.TERMINAL
