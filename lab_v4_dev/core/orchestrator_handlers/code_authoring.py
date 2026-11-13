"""Code analysis handler; provider use is delegated to the central authorization callback."""

import os


def handle_analyze_code(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    if authorized_ask is None:
        return {"status": "unavailable", "intent": intent, "source": "provider_policy", "text": "بوابة المزود المصرح بها غير متاحة لهذا المسار."}
    from lab_v4_dev.awareness.project_memory import load_memory
    from lab_v4_dev.config.provider_config import get_active_provider
    from lab_v4_dev.core.code_engine import analyze_code
    code_text = orchestrator.context.last_result.get("code","") if orchestrator.context.last_result else ""
    # إذا لم يحدد المستخدم ملفاً ولا يوجد كود سابق → طلب توضيح
    vague = ["هذا الملف","الملف","الكود","هذا","هذا الكود","حلل"]
    if not code_text and not target and any(v == raw.strip() for v in vague):
        return {"status":"needs_clarification","intent":intent,
                "text":"أي ملف تريد تحليله؟ اكتب اسم الملف أو مساره."}
    if not code_text and target:
        # قراءة ملف محدد
        try:
            full = os.path.expanduser(target)
            code_text = open(full, encoding="utf-8", errors="ignore").read()[:3000]
        except:
            return {"status":"failed","text":f"لا يمكن قراءة: {target}"}
    if not code_text:
        # لا كود محدد → اقرأ الملفات الحرجة فعلياً
        memory = load_memory()
        critical = [c["file"] for c in memory.get("critical_files",[])][:4]
        if not critical:
            critical = ["lab_v4_dev/core/orchestrator.py","lab_v4_dev/core/agent.py"]
        parts = []
        for cf in critical:
            try:
                from lab_v4_dev.core.project_context import get_active_project_root
                fp = os.path.join(get_active_project_root(), cf)
                content = open(fp, encoding="utf-8", errors="ignore").read()[:800]
                parts.append("=== " + cf + " ===\n" + content)
            except:
                pass
        code_text = "\n\n".join(parts)
    prompt = f"أنت خبير أمن سيبراني وبرمجة. حلل الكود التالي وأجب على: {raw}\n\nالكود:\n{code_text}"
    result = authorized_ask(prompt, max_tokens=600)
    text = result.get("text","")
    if text:
        from lab_v4_dev.intent.response_cache import save as rcache_save
        rcache_save(str(intent), target or "", text)
    # ─── تسجيل الملف كمحلل ───
    if target and result.get("status") == "success":
        orchestrator._analyzed_files.add(target)
    # ─── حفظ الموضوع في السياق ───
    if text and result.get("status") == "success":
        orchestrator.context.current_subject = raw
    return {
        "status" : result.get("status","success"),
        "intent" : intent,
        "source" : result.get("provider_used", get_active_provider()),
        "text"   : text,
    }


def handle_generate_code(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    from lab_v4_dev.core.code_engine import generate_code
    result = generate_code(raw, authorized_ask=authorized_ask)
    if result["status"] != "success":
        return {"status": result["status"], "intent": intent, "text": result.get("text", "فشل في كتابة الكود")}
    return {
        "success": True,
        "status": "success",
        "intent": intent,
        "text": result.get("explanation", ""),
        "code": result.get("code", ""),
        "saved_to": result.get("saved_to"),
    }


__all__ = ["handle_analyze_code", "handle_generate_code"]
