# CyberLab Agent v4.6
# context/context_resolver.py

from lab_v4.intent.intents import Intent

RESULT_KEYWORDS = ["نتيجة","اعرض نتيجة","اكتب نتيجة","ما النتيجة","نتائج"]
REPEAT_KEYWORDS = ["كرر","اعد","مرة ثانية","مرة اخرى"]

def bind_context(intent: str, text: str, store) -> dict:

    # CASE 1: يطلب نتيجة آخر أمر
    if any(kw in text for kw in RESULT_KEYWORDS):
        return {
            "intent" : "show_last_result",
            "target" : store.last_target,
            "data"   : store.last_result,
        }

    # CASE 2: يطلب تكرار آخر أمر
    if any(kw in text for kw in REPEAT_KEYWORDS):
        return {
            "intent" : store.last_intent or intent,
            "target" : store.last_target,
            "data"   : None,
        }

    # CASE 3: intent غير واضح — استخدم السياق
    if intent == Intent.UNCLEAR:
        if store.last_intent:
            return {
                "intent" : store.last_intent,
                "target" : store.last_target,
                "data"   : None,
            }

    # CASE 4: تدفق طبيعي
    return {
        "intent" : intent,
        "target" : None,
        "data"   : None,
    }
