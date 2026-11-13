"""Local knowledge and capability handlers."""

def handle_capabilities(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.project_context import get_active_project as _gap
    from lab_v4_dev.awareness.project_memory import load_memory
    from lab_v4_dev.core.project_context import get_active_project as _gap
    _proj = _gap()
    _mem  = load_memory()
    _total = _mem.get("total_files", 0)
    _lines = [
        "=== CyberLab Agent ===",
        "",
        "فهم المشاريع: Python وTypeScript • الاعتماديات • نقاط الدخول • الملفات الحرجة",
        "تحليل الأخطاء: كشف • تحليل • إصلاح • تعلم تلقائي",
        "كتابة الكود: سكريبتات Python • تشغيل وتحليل",
        "الأمن السيبراني: شرح مفاهيم • حفظ محلي",
        "الذاكرة: حفظ الجلسات • سياق العمل",
        "",
        f"المشروع الحالي: {_proj.name} ({_total} ملف)",
    ]
    return {"status":"success","intent":intent,"source":"local",
            "text":"\n".join(_lines)}


def handle_save_kb(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.knowledge_base import store
    from lab_v4_dev.awareness.knowledge_base import store
    pending = getattr(orchestrator.context, "pending_save", None)
    last = orchestrator.context.last_result or {}
    topic = pending or last.get("pending_save")
    answer = last.get("text", "")
    if topic and answer:
        store(topic, answer, confirmed=True, confidence="EXPLICIT")
        orchestrator.context.pending_save = None
        return {"status":"success","intent":intent,
                "text":"✅ تم الحفظ في الذاكرة المحلية"}
    return {"status":"success","intent":intent,
            "text":"⚠️ لا يوجد شرح معلق للحفظ"}


def handle_skip_kb(orchestrator, intent, *, target=None, raw=None):
    orchestrator.context.pending_save = None
    return {"status":"success","intent":intent,
            "text":"⏭️ تم التجاوز — لن يُحفظ هذا الشرح"}


def handle_cyber_explain(
    orchestrator, intent, *, target=None, raw=None, authorized_ask=None,
    response_attributes=None, conversation_history=None, context_transition=None,
):
    import os
    from lab_v4_dev.config.provider_config import get_active_provider
    if authorized_ask is None:
        return {
            "status": "unavailable", "intent": intent,
            "source": "provider_policy",
            "text": "بوابة المزود المصرح بها غير متاحة لهذا المسار.",
        }
    from lab_v4_dev.awareness.knowledge_base import search, store, hit
    is_continuation = context_transition in {
        "continue", "restore", "reference", "clarification",
    }
    cached = None if response_attributes or is_continuation else search(raw)
    if cached:
        hit(raw)
        orchestrator.context.current_subject = raw
        return {
            "status": "success",
            "intent": intent,
            "source": "local_kb",
            "text"  : f"[من الذاكرة المحلية]\n{cached}",
        }
    # ─── Hallucination Guard ───
    import re as _re
    _file_extensions = (
        ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml",
        ".yml", ".md", ".txt", ".sh", ".html", ".css", ".sql",
    )
    _explicit_file = bool(
        isinstance(target, str)
        and ("/" in target or "\\" in target
             or target.lower().endswith(_file_extensions))
    )
    _fake_pattern = _re.compile(r'[A-Z0-9_]{6,}', _re.UNICODE)
    _words = raw.replace("اشرح","").replace("شرح","").replace("ميزة","").replace("ما هو","").replace("ما هي","").strip()
    _has_fake = bool(_fake_pattern.search(_words))
    if _has_fake and _explicit_file:
        _found_in_project = False
        try:
            import json as _json
            _mem_path = "lab_v4_dev/cache/project_memory.json"
            with open(_mem_path, encoding="utf-8") as _f:
                _mem = _json.load(_f)
            _mem_str = _json.dumps(_mem, ensure_ascii=False).lower()
            _found_in_project = _words.lower() in _mem_str
        except:
            pass
        if not _found_in_project:
            return {
                "status": "success",
                "intent": intent,
                "source": "guard",
        "text": f"❌ '{_words}' غير موجودة في المشروع ولا في قاعدة المعرفة. لا أستطيع الإجابة بدون مصدر حقيقي.",
            }
    # ─── كشف ملفات المشروع عبر project_index ───
    _project_file_code = None
    
    if target and _explicit_file:
        _candidates = [
            target,
            os.path.join("lab_v4_dev", target),
        ]
    
        # البحث المباشر
        for _c in _candidates:
            if os.path.exists(_c):
                try:
                    _project_file_code = open(_c, encoding="utf-8").read()[:3000]
                except:
                    pass
                break
    
        # البحث عبر فهرس المشروع
        if not _project_file_code:
            try:
                import json as _json
                from lab_v4_dev.awareness.project_index import _index_file
    
                with open(_index_file(), encoding="utf-8") as _f:
                    _idx = _json.load(_f)
    
                for _path, _info in _idx.items():
                    if os.path.basename(_path) == os.path.basename(target):
                        _real = _info.get("path", "")
                        if _real and os.path.exists(_real):
                            _code = open(
                                _real,
                                encoding="utf-8"
                            ).read()[:3000]
    
                            _functions = _info.get("functions", [])
                            _role = _info.get("role", "")
    
                            _project_file_code = f"""
    FILE PATH:
    {_path}
    
    PROJECT ROLE:
    {_role}
    
    KNOWN FUNCTIONS:
    {_functions}
    
    SOURCE CODE:
    {_code}
    """
                            target = _path
                            break
            except Exception:
                pass
    
    # ─── البصمة الشخصية ───
    try:
        from lab_v4_dev.user_data.profile_loader import load_profile
        _profile = load_profile()
        _style = _profile.get("explanation_style", {})
    except:
        _style = {}
    _instructions = []
    if _style.get("step_by_step", True):
        _instructions.append("اشرح خطوة بخطوة مرقمة")
    if _style.get("show_risks", True):
        _instructions.append("اذكر المخاطر والتداعيات دائماً")
    if _style.get("examples_required", True):
        _instructions.append("أعطِ مثالاً عملياً (كود أو سيناريو)")
    if _style.get("show_reasoning", True):
        _instructions.append("وضح سبب كل خطوة")
    _extra = "\n".join(f"- {i}" for i in _instructions)
    
    _prompt = raw
    if _project_file_code:
        system = f"""أنت مهندس برمجيات خبير يحلل ملفات مشروع Python.
    
    مهمتك تحليل الملف الموجود أدناه فقط.
    ممنوع:
    - اختراع دوال غير موجودة
    - افتراض مكتبات أو ملفات غير ظاهرة
    - إعطاء شرح عام عن اسم الملف فقط
    
    اتبع هذا الترتيب:
    1. وظيفة الملف حسب الكود الحقيقي.
    2. الدوال الموجودة فعلياً فقط.
    3. العلاقات مع المشروع إذا ظهرت من الكود.
    4. ملخص قصير.
    
    إذا لم تجد معلومة في الكود قل: غير موجود في الملف.
    
    
    قواعد الشرح الصارمة:
    - اعتمد فقط على المسار والـ metadata والكود الحقيقي.
    - لا تستخدم كلمات مثل: يبدو، قد يكون، ربما.
    - لا تستنتج ملفات أو علاقات غير موجودة في البيانات.
    - لا تضف مخاطر أو هجمات أو أمثلة خارج الملف.
    - إذا لم تكن العلاقة موجودة في الكود قل: غير موجود في البيانات المتاحة.
    الكود الحقيقي:
    {_project_file_code}"""
    elif _explicit_file:
        system = f"""أنت محلل كود Python في مشروع CyberLab Agent.
    
    قواعد صارمة:
    - اعتمد فقط على المسار والـ metadata والكود الحقيقي المعطى.
    - لا تخترع دوال أو ملفات أو علاقات غير موجودة.
    - لا تضف أمثلة هجوم أو مخاطر أمنية عامة.
    - لا تستخدم كلمات: يبدو، قد يكون، ربما.
    - إذا لم توجد معلومة في الكود قل: غير موجود في الملف.
    
    اتبع الترتيب:
    1. وظيفة الملف حسب الكود الحقيقي.
    2. الدوال الموجودة فعلياً فقط.
    3. العلاقات مع المشروع إذا ظهرت من الكود.
    4. ملخص قصير.
    
    الكود الحقيقي:
    {_project_file_code}"""
    else:
        from lab_v4_dev.llm.prompt_builder import build_cybersec_prompt
        system, _prompt = build_cybersec_prompt(
            raw,
            history=conversation_history,
            continuation=bool(context_transition in {
                "continue", "restore", "reference",
            }),
        )
    
    if response_attributes:
        from lab_v4_dev.llm.prompt_builder import (
            format_response_attribute_instructions,
        )
        style_instructions = format_response_attribute_instructions(
            response_attributes
        )
        if style_instructions:
            system += "\n\n" + style_instructions
    
    result = authorized_ask(
        _prompt,
        system=system,
        max_tokens=2000
    )
    answer = str(result.get("text") or "").strip()
    if result.get("status") != "success" or not answer:
        # Give a truthful high-level failure class without exposing
        # prompts, redaction spans, secrets, or provider metadata.
        error = result.get("error") or {}
        error_code = str(
            error.get("code", "") if isinstance(error, dict) else error
        ).upper()
        if error_code.startswith("PRIVACY_") or error_code == "PRIVACY_EXTERNAL_BLOCKED":
            answer = (
                "أوقفت بوابة الخصوصية هذا الطلب قبل إرسال البيانات المحمية "
                "إلى مزود خارجي. يمكنك طرح السؤال بصياغة لا تتضمن تلك البيانات."
            )
        elif error_code.startswith(("PROVIDER_", "LLM_", "NETWORK_")):
            answer = "تعذر الوصول إلى مزود اللغة. لم يُحفظ شرح جديد؛ يمكنك المحاولة لاحقًا."
        else:
            answer = "تعذر إكمال الشرح بسبب خطأ داخلي. لم يُحفظ شرح جديد."
    # ─── حفظ الموضوع في السياق ───
    if result.get("status") == "success":
        orchestrator.context.current_subject = raw
    return {
        "status"       : result.get("status","failed"),
        "intent"       : intent,
        "source"       : get_active_provider(),
        "text"         : answer,
        "pending_save" : raw if result.get("status") == "success" and str(result.get("text") or "").strip() else None,
        "pending_confirmation": (
            {"kind": "save_kb", "topic": raw}
            if result.get("status") == "success" and str(result.get("text") or "").strip() else None
        ),
        # Never ask to save a response that was not successfully produced.
        "save_prompt"  : (
            "💾 هل تحفظ هذا الشرح في الذاكرة المحلية؟ (نعم / لا / تجاوز)"
            if result.get("status") == "success" and str(result.get("text") or "").strip()
            else None
        ),
    }
    
        # ─── Project Timeline ───

__all__ = ["handle_capabilities", "handle_save_kb", "handle_skip_kb", "handle_cyber_explain"]
