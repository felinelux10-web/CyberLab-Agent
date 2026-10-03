"""
LLM Intent Resolver — P08 provider-neutral boundary
يُستدعى فقط عند فشل القاموس والـ Cache.
يسأل LLM Gateway: ما الـ intent المناسب لهذه الجملة؟
"""
from lab_v4_dev.llm.gateway import ask
from lab_v4_dev.intent.intent_cache import save
from lab_v4_dev.intent.intents import Intent

VALID_INTENTS = tuple(dict.fromkeys(
    value
    for name, value in vars(Intent).items()
    if name.isupper() and isinstance(value, str)
))

PROMPT_TEMPLATE = """أنت محدد نوايا (Intent Classifier) لوكيل برمجي عربي.

قائمة الـ intents المتاحة:
{intents}

الجملة: "{text}"

أجب بكلمة واحدة فقط: اسم الـ intent المناسب من القائمة أعلاه.
إذا لم تجد مناسباً اكتب: unclear
لا تكتب أي شيء آخر."""

def resolve(text: str) -> str:
    """يسأل LLM Gateway عن الـ intent، يحفظ النتيجة في Cache، يعيدها."""
    try:
        prompt = PROMPT_TEMPLATE.format(
            intents="\n".join(f"- {i}" for i in VALID_INTENTS),
            text=text
        )
        raw = ask(prompt)
        response = (raw.get("text","") if isinstance(raw, dict) else raw).strip().lower().replace("-","_")
        intent = response if response in VALID_INTENTS else "unclear"
        if intent != "unclear":
            save(text, intent)
        return intent
    except Exception:
        return "unclear"
