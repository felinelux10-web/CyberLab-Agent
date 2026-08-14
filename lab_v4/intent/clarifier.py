# CyberLab Agent v4.0
# intent/clarifier.py

CLARIFICATION_QUESTIONS = {
    "no_action": "ماذا تريد أن أفعل؟ (شغّل / اكتب / اقرأ)",
    "no_target": "على أي ملف أو أمر تريد التنفيذ؟",
    "too_vague": "هل تقصد: تشغيل أمر، كتابة ملف، أو قراءة ملف؟",
}

def needs_clarification(parsed: dict) -> bool:
    return parsed.get("status") == "unclear"

def get_question(parsed: dict) -> str:
    raw = parsed.get("raw", "")
    action = parsed.get("action")
    target = parsed.get("target", "")

    if not action:
        return CLARIFICATION_QUESTIONS["no_action"]

    if not target:
        return CLARIFICATION_QUESTIONS["no_target"]

    return CLARIFICATION_QUESTIONS["too_vague"]

def clarify(parsed: dict) -> dict:
    if not needs_clarification(parsed):
        return {"needed": False}

    question = get_question(parsed)
    return {
        "needed"  : True,
        "question": question,
        "raw"     : parsed.get("raw", ""),
    }
