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
    route  = guarded["route"]
    intent = guarded["intent"]
    raw    = guarded["raw"]

    if route == "clarify":
        return {"status":"unclear","message":"؟ لم أفهم — حاول بطريقة أخرى"}

    if route == get_active_provider():
        try:
            from lab_v4_dev.llm.gateway import ask
            from lab_v4_dev.llm.context_builder import build_system_prompt
            system = build_system_prompt(agent.db)
            result = ask(raw, system=system, max_tokens=400)
            if result["status"] == "success":
                return {
                    "status": "success",
                    "source": get_active_provider(),
                    "text"  : result["text"],
                    "intent": intent,
                }
        except Exception:
            pass
        # Fallback محلي
        return agent.orchestrator.handle(raw)

    return agent.orchestrator.handle(raw)
