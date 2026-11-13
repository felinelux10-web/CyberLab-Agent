# CyberLab Agent v4.6
# core/guard.py

from lab_v4_dev.intent.intents import Intent


def guard(parsed: dict) -> dict:
    """Legacy classifier adapter; provider and execution ownership stay in ConversationManager."""
    intent = parsed["intent"]
    text = str(parsed.get("raw") or "")
    context = parsed.get("context", "general")
    route = "clarify" if intent == Intent.UNCLEAR else "conversation_manager"

    return {
        "intent": intent,
        "target": parsed.get("target", ""),
        "context": context,
        "route": route,
        "raw": text,
    }


def execute(guarded: dict, agent) -> dict:
    """Compatibility adapter; never calls a provider or Orchestrator directly."""
    raw = str(guarded.get("raw") or "")
    if guarded.get("route") == "clarify":
        return {
            "status": "needs_clarification",
            "source": "guard_compatibility",
            "executed": False,
            "text": "لم يتضح الطلب؛ يلزم توضيح المقصود.",
        }

    manager = getattr(agent, "conv_manager", None)
    process = getattr(manager, "process", None)
    if not callable(process):
        return {
            "status": "denied",
            "source": "guard_route_required",
            "executed": False,
            "text": "مسار Guard القديم لا يملك صلاحية استدعاء المزود أو Orchestrator مباشرة.",
        }
    return process(raw)
