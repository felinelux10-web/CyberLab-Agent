# CyberLab Agent v4.8
# core/task_chain.py

import re

# كلمات الربط بين الخطوات
CHAIN_KEYWORDS = ["ثم", "بعدها", "وبعد", "ثم اعرض", "ثم قارن", "ثم احفظ"]
MAX_STEPS = 20

def detect_chain(text: str) -> list:
    """يكشف إذا كان الأمر متعدد الخطوات ويقسمه"""
    for kw in CHAIN_KEYWORDS:
        if re.search(r'(?<!\w)' + re.escape(kw) + r'(?!\w)', text):
            parts = re.split(r'(?<!\w)' + re.escape(kw) + r'(?!\w)', text, MAX_STEPS - 1)
            steps = [p.strip() for p in parts if p.strip()]
            if len(steps) > 1:
                return steps[:MAX_STEPS]
    return []

def is_chain(text: str) -> bool:
    return any(re.search(r'(?<!\w)' + re.escape(kw) + r'(?!\w)', text) for kw in CHAIN_KEYWORDS)

def execute_chain(steps: list, orchestrator) -> dict:
    """ينفذ الخطوات بالترتيب مع state passing حقيقي"""
    results    = []
    last_result = None
    chain_state = {}  # state مشترك بين الخطوات

    for i, step in enumerate(steps):
        # أضف سياق من الخطوة السابقة
        if last_result:
            # احقن النتيجة السابقة في السياق
            # DNI-10: بعض النوايا (مثل read_file) تُرجع المحتوى في "output" وليس "text"
            _last_text = last_result.get("text") or last_result.get("output") or ""
            if _last_text:
                orchestrator.context.current_analysis = _last_text[:200]
            last_file = (
                last_result.get("saved_to")
                or last_result.get("file")
                or ""
            )
            if last_file:
                chain_state["last_file"] = last_file
                orchestrator.context.current_file = last_file

            # حل الضمائر
            ref_words = ["نتيجته","نتيجتها","منه","عنه","فيه","هذا"]
            if any(w in step for w in ref_words):
                subject = (
                    orchestrator.context.current_file
                    or orchestrator.context.current_subject
                    or ""
                )
                if subject:
                    step = step + f" {subject}"

        # DNI-10: حفظ target من parser للسياق قبل تنفيذ الخطوة التالية
        try:
            from lab_v4_dev.intent.intent_parser import parse
            parsed_step = parse(step)
            if parsed_step.get("target"):
                orchestrator.context.current_file = parsed_step["target"]
            elif parsed_step.get("intent") == "read_file":
                orchestrator.context.current_file = parsed_step.get("target","")
        except Exception:
            pass

        # DNI-10: inherit target for pronoun commands inside chain
        try:
            from lab_v4_dev.intent.intent_parser import parse

            parsed_step = parse(step)

            if parsed_step.get("intent") == "delete_file" and not parsed_step.get("target"):
                current = getattr(orchestrator.context, "current_file", "")
                if current:
                    step = step + " " + current

        except Exception:
            pass

        result = orchestrator.handle(step)
        _step_text = result.get("text") or result.get("output") or ""
        results.append({
            "step"  : i + 1,
            "cmd"   : step,
            "status": result.get("status","?"),
            "text"  : _step_text[:300],
            "source": result.get("source","local"),
        })
        last_result = result
        chain_state[f"step_{i+1}"] = result.get("status","?")

        # توقف عند فشل حقيقي
        if result.get("status") in ["failed","error","timeout"]:
            results[-1]["stopped_chain"] = True
            break

    return {
        "status" : "success",
        "intent" : "task_chain",
        "steps"  : len(results),
        "results": results,
    }
