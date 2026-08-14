# CyberLab Agent v4.6
# llm/smart_router.py

from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.config.provider_config import get_active_provider

# Intents تحتاج Groq
GROQ_INTENTS = {
    Intent.PROJECT_SCAN, Intent.DIAGNOSE,
    Intent.PROPOSE_SOLUTION, Intent.PROPOSE_FIX,
    Intent.IMPACT_ANALYSIS, Intent.RISK_ANALYSIS,
    Intent.PLAN, Intent.DECOMPOSE,
    Intent.REFACTOR_FILE, Intent.CLEANUP_CODE,
    Intent.GENERATE_TEST, Intent.PROGRESS_REPORT,
    Intent.PROJECT_REPORT, Intent.REMAINING_WORK,
}

COMPLEXITY_KEYWORDS = [
    "اقترح","خطة","تحليل","شرح","لماذا","كيف",
    "فسر","وضح","قارن","حدد","استخرج",
]

def decide(intent: str, text: str, groq_available: bool = True) -> str:
    if not groq_available:
        return "local"
    
    # طويل + تحليلي → Groq
    if len(text) > 20 and any(kw in text for kw in COMPLEXITY_KEYWORDS):
        return get_active_provider()
    
    # intent يحتاج Groq
    if intent in GROQ_INTENTS:
        return get_active_provider()
    
    return "local"

def ask_with_fallback(prompt: str, system: str = None, max_tokens: int = 300) -> dict:
    try:
        from lab_v4_dev.llm.gateway import ask
        result = ask(prompt, system=system, max_tokens=max_tokens)
        if result["status"] == "success":
            return result
        # Groq فشل → fallback
        return {
            "status": "fallback",
            "text"  : "لم أتمكن من الاتصال بـ Groq. الرجاء المحاولة لاحقاً.",
            "source": "local_fallback",
        }
    except Exception as e:
        return {
            "status": "fallback",
            "text"  : "لا يوجد اتصال بالإنترنت. أعمل محلياً.",
            "source": "local_fallback",
        }
