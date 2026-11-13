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


def handle_modify_code(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    import os
    from lab_v4_dev.core.symbol_resolver import resolve as sym_resolve
    from lab_v4_dev.core.surgical_editor import extract_symbol, patch_symbol, clean_llm_output, validate_patch
    from lab_v4_dev.core.code_engine import modify_code
    from lab_v4_dev.executor.safe_pipeline import SafePipeline

    raw_text = str(raw or "")
    if len(raw_text.strip().split()) < 2:
        return {"status": "needs_target", "intent": intent, "text": "ماذا تريد أن أعدل؟"}

    context_file = getattr(orchestrator.context, "current_file", None)
    if context_file and not os.path.isfile(os.path.expanduser(str(context_file))):
        context_file = ""
    resolved = sym_resolve(raw_text, target or context_file or "")
    if resolved.get("ambiguous"):
        candidates = [item.get("file", "") for item in resolved.get("candidates", [])]
        return {
            "status": "needs_clarification", "intent": intent,
            "text": "وجدت أكثر من ملف مرشح. حدّد الملف: " + "، ".join(candidates[:5]),
            "candidates": candidates,
        }
    if not resolved.get("found"):
        return {"status": "needs_target", "intent": intent, "text": "لم أجد الملف أو الدالة"}

    file_path, symbol = resolved["file"], resolved["symbol"]
    symbol_data = extract_symbol(file_path, symbol) if symbol else {}
    is_surgical = bool(symbol_data.get("code"))
    if is_surgical:
        code_text = symbol_data["code"]
    else:
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as handle:
                code_text = handle.read()
        except OSError:
            return {"status": "failed", "intent": intent, "text": "لا يمكن قراءة الملف"}
    if not code_text:
        return {"status": "failed", "intent": intent, "text": "لا يوجد كود"}

    result = modify_code(code_text, raw_text, authorized_ask=authorized_ask)
    if result.get("status") != "success" or not result.get("code"):
        return {
            "status": result.get("status", "failed"), "intent": intent,
            "text": result.get("text", result.get("explanation", "")),
        }

    with open(file_path, encoding="utf-8") as handle:
        original_source = handle.read()
    if is_surgical:
        clean_code = clean_llm_output(result["code"], symbol)
        final_code = patch_symbol(
            original_source, symbol, clean_code,
            symbol_data["start_line"], symbol_data["end_line"],
        )
    else:
        final_code = result["code"]

    validation = validate_patch(original_source, final_code)
    if not validation.get("ok"):
        return {"status": "failed", "intent": intent, "text": "❌ غير آمن: " + str(validation)}
    if final_code == original_source:
        return {"status": "failed", "intent": intent, "text": "لم ينتج التعديل أي تغيير في الملف"}

    try:
        database = orchestrator.agent.db
        if database is not None and getattr(database, "conn", None) is None:
            database.connect()
        pipeline = getattr(orchestrator, "pipeline", None) or SafePipeline(database)
        pipeline_result = pipeline.execute(
            {"files": [file_path], "reason": raw_text},
            {file_path: final_code},
        )
        mode = "surgical" if is_surgical else "full"
        if pipeline_result.get("status") == "success":
            if not os.path.isfile(file_path):
                return {"status": "failed", "intent": intent, "text": "فشل التحقق: الملف غير موجود بعد الكتابة"}
            with open(file_path, encoding="utf-8") as handle:
                after_source = handle.read()
            if after_source != final_code:
                return {"status": "failed", "intent": intent, "text": "فشل التحقق: المحتوى المكتوب لا يطابق التعديل"}
            orchestrator.context.current_file = file_path
            return {
                "status": "success", "intent": intent,
                "text": "✅ [" + mode + "] " + (symbol or file_path.split("/")[-1]),
                "file": file_path, "verified": True,
            }
        return {"status": "failed", "intent": intent, "text": "❌ " + str(pipeline_result.get("reason", ""))}
    except Exception as exc:
        return {"status": "failed", "intent": intent, "text": str(exc)}


__all__ = ["handle_analyze_code", "handle_generate_code", "handle_modify_code"]
