# CyberLab Agent v4.6
# core/guard.py

from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.config.provider_config import get_active_provider

GROQ_INTENTS = {
    Intent.PROJECT_SCAN, Intent.DIAGNOSE,
    Intent.PROPOSE_SOLUTION, Intent.PROPOSE_FIX,
    Intent.IMPACT_ANALYSIS, Intent.RISK_ANALYSIS,
    Intent.PLAN, Intent.DECOMPOSE,
    Intent.REFACTOR_FILE, Intent.CLEANUP_CODE,
    Intent.GENERATE_TEST, Intent.PROGRESS_REPORT,
    Intent.PROJECT_REPORT, Intent.REMAINING_WORK,
}

def guard(parsed: dict) -> dict:
    intent = parsed["intent"]
    text   = parsed["raw"]
    ctx    = parsed.get("context","general")

    if intent == Intent.UNCLEAR:
        route = "clarify"
    elif intent in GROQ_INTENTS:
        route = get_active_provider()
    elif len(text) > 25 and ctx == "project_level":
        route = get_active_provider()
    else:
        route = "local"

    return {
        "intent" : intent,
        "target" : parsed.get("target",""),
        "context": ctx,
        "route"  : route,
        "raw"    : text,
    }

def execute(guarded: dict, agent) -> dict:
    """Compatibility adapter; ConversationManager owns routing and provider policy."""
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
