# CyberLab Agent v4.6
# lab_v4/llm/router.py

from lab_v4.intent.intents import Intent

# Intents تحتاج Groq
GROQ_INTENTS = [
    Intent.PROJECT_SCAN,
    Intent.DIAGNOSE,
    Intent.PROPOSE_SOLUTION,
    Intent.PROPOSE_FIX,
    Intent.IMPACT_ANALYSIS,
    Intent.RISK_ANALYSIS,
    Intent.PLAN,
    Intent.DECOMPOSE,
    Intent.REFACTOR_FILE,
    Intent.CLEANUP_CODE,
    Intent.OPTIMIZE_CODE,
    Intent.GENERATE_TEST,
    Intent.PROJECT_REPORT,
    Intent.PROGRESS_REPORT,
    Intent.REMAINING_WORK,
    Intent.PROJECT_PURPOSE,
    Intent.ARCHITECTURE,
]

# Intents تعمل محلياً
LOCAL_INTENTS = [
    Intent.STATUS,
    Intent.SPACE,
    Intent.CLEAN,
    Intent.HEALTH,
    Intent.REPORT,
    Intent.SESSION_REPORT,
    Intent.HISTORY,
    Intent.TODO_LIST,
    Intent.TODO_ADD,
    Intent.SCHEDULE,
    Intent.NOTE,
    Intent.DRAFT,
    Intent.LOGS,
    Intent.HELP,
    Intent.READ_FILE,
    Intent.SHOW_CHANGES,
    Intent.CONTEXT_REPORT,
    Intent.MEMORY_STATUS,
    Intent.SNAPSHOT,
    Intent.LIST_SNAPSHOTS,
]

def needs_llm(intent: str) -> bool:
    return intent in GROQ_INTENTS

def is_local(intent: str) -> bool:
    return intent in LOCAL_INTENTS

def route(intent: str) -> str:
    if needs_llm(intent):
        return "groq"
    return "local"
