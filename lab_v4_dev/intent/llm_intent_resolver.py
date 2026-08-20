"""
LLM Intent Resolver — P08 provider-neutral boundary
يُستدعى فقط عند فشل القاموس والـ Cache.
يسأل LLM Gateway: ما الـ intent المناسب لهذه الجملة؟
"""
from lab_v4_dev.llm.gateway import ask
from lab_v4_dev.intent.intent_cache import save

VALID_INTENTS = [
    "work_context","work_status","context_report","system_status",
    "project_scan","project_report","project_index","project_map",
    "read_file","modify_code","generate_code","analyze_code",
    "search_code","file_impact","impact_chain_query","criticality_query",
    "dependents_query","entry_point_query","dependency_map",
    "repair_analyze","repair_approve","repair_reject","pending_fixes",
    "session_save","session_restore","run_history","run_script",
    "self_diagnose","full_diagnose","health","status","space",
    "help","todo_list","todo_add","note","release_index","analyze_release",
    "compare_versions","switch_project","read_external_project",
    "unclear"
]

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
