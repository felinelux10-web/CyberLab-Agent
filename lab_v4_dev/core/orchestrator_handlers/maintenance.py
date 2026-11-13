"""Non-destructive maintenance intent handlers."""


def handle_clean(orchestrator, intent, *, target=None, raw=None):
    return {
        "status": "needs_clarification",
        "intent": intent,
        "text": "ما الذي تريد تنظيفه؟ حدّد الهدف قبل المتابعة.",
    }


__all__ = ["handle_clean"]
