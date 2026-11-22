"""Compatibility boundary for older integrations; never selects an Orchestrator or provider."""
from __future__ import annotations

from lab_v4_dev.intent.intents import Intent


def guard(request):
    request = request if isinstance(request, dict) else {}
    intent = request.get("intent")
    if (
        intent == getattr(Intent, "UNCLEAR", None)
        or str(getattr(intent, "value", intent) or "").casefold() in {"unclear", "unknown"}
    ):
        return {
            "route": "clarify",
            "intent": intent,
            "raw": str(request.get("raw") or request.get("text") or ""),
        }
    return {
        "route": "conversation_manager",
        "intent": intent,
        "raw": str(request.get("raw") or request.get("text") or ""),
    }


def execute(decision, agent):
    decision = decision if isinstance(decision, dict) else {}
    if decision.get("route") != "conversation_manager":
        return {
            "status": "needs_clarification",
            "source": "guard_route_required",
            "executed": False,
        }
    manager = getattr(agent, "conv_manager", None)
    process = getattr(manager, "process", None)
    if not callable(process):
        return {
            "status": "denied",
            "source": "guard_route_required",
            "executed": False,
        }
    raw = str(decision.get("raw") or "")
    if not raw:
        return {
            "status": "needs_clarification",
            "source": "guard_empty_request",
            "executed": False,
        }
    return process(raw)
