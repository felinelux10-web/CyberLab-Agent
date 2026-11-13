"""Release metadata and timeline handlers."""

def handle_last_project(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.project_knowledge import get_project_history
    hist = get_project_history()
    last = hist.get("last_project","?")
    last_root = hist.get("last_root","?")
    history = hist.get("history",[])
    lines = [f"آخر مشروع: {last}", f"المسار: {last_root}", ""]
    if len(history) > 1:
        lines.append("المشاريع السابقة:")
        for h in history[1:4]:
            lines.append(f"  - {h['name']} ({h['last_used']})")
    return {"status":"success","intent":intent,"text":chr(10).join(lines)}


def handle_current_version(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.project_metadata import ProjectMetadata
    version = ProjectMetadata().get_version()
    return {"status":"success","intent":intent,
            "text":f"الإصدار الحالي: {version}"}


def handle_release_index(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.release_analyzer import get_available_versions
    versions = get_available_versions()
    return {
        "status"  : "success",
        "intent"  : intent,
        "text"    : "الإصدارات المتاحة: " + ", ".join(versions),
        "versions": versions,
    }


def handle_analyze_release(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    if authorized_ask is None:
        return {"status": "unavailable", "intent": intent, "source": "provider_policy", "text": "بوابة المزود المصرح بها غير متاحة لهذا المسار."}
    from lab_v4_dev.config.provider_config import get_active_provider
    from lab_v4_dev.awareness.release_analyzer import (
        load_release, extract_version_from_text
    )
    ver = extract_version_from_text(target or raw)
    if not ver:
        ver = orchestrator.context.current_version
    if not ver:
        return {"status":"needs_target","message":"أي إصدار؟ مثال: حلل الإصدار 4.1"}
    release = load_release(ver)
    if not release["content"]:
        return {"status":"failed","message":f"لا يوجد تقرير للإصدار {ver}"}
    content = release["content"][:800]
    from lab_v4_dev.llm.prompt_builder import build_release_prompt
    prompt  = build_release_prompt(ver, content, raw)
    result = authorized_ask(prompt, system="أنت مساعد هندسي. أجب فقط من التقرير المعطى.", max_tokens=400)
    orchestrator.context.current_version = ver
    orchestrator.context.current_subject = f"version_{ver}"
    return {
        "status" : result["status"],
        "intent" : intent,
        "source" : result.get("provider_used", get_active_provider()),
        "version": ver,
        "text"   : result.get("text",""),
    }


def handle_compare_versions(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    if authorized_ask is None:
        return {"status": "unavailable", "intent": intent, "source": "provider_policy", "text": "بوابة المزود المصرح بها غير متاحة لهذا المسار."}
    from lab_v4_dev.config.provider_config import get_active_provider
    from lab_v4_dev.awareness.release_analyzer import (
        compare_versions, extract_version_from_text
    )
    import re
    versions = re.findall(r"v?4\.\d", raw)
    if len(versions) < 2:
        return {"status":"needs_target","message":"حدد إصدارين. مثال: قارن بين 4.4 و 4.6"}
    v1 = f"v{versions[0]}" if not versions[0].startswith("v") else versions[0]
    v2 = f"v{versions[1]}" if not versions[1].startswith("v") else versions[1]
    data = compare_versions(v1, v2)
    if not data["both_ok"]:
        return {"status":"failed","message":f"لا يوجد تقرير لأحد الإصدارين"}
    prompt = (
        f"قارن بين الإصدارين:\n\n"
        f"=== {v1} ===\n{data['v1']['content'][:400]}\n\n"
        f"=== {v2} ===\n{data['v2']['content'][:400]}\n\n"
        f"أجب بالعربية: ما الفروقات الرئيسية؟"
    )
    system = "أنت مساعد هندسي متخصص في تحليل إصدارات البرمجيات. أجب بإيجاز."
    result = authorized_ask(prompt, system=system, max_tokens=400)
    return {
        "status": result["status"],
        "intent": intent,
        "source": result.get("provider_used", get_active_provider()),
        "v1"    : v1,
        "v2"    : v2,
        "text"  : result.get("text",""),
    }


def handle_project_timeline(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.data.project_timeline import (
        init_timeline, get_full_history, get_version_events
    )
    init_timeline()
    # هل يسأل عن إصدار محدد؟
    ver = orchestrator.context.current_version
    import re
    m = re.search(r"v?4\.\d", raw)
    if m:
        ver = m.group(0) if m.group(0).startswith("v") else "v"+m.group(0)
    if ver:
        events = get_version_events(ver)
        text = f"أحداث {ver}:\n"
        text += "\n".join(f"  - {e['event']}" for e in events) or "لا توجد أحداث"
    else:
        text = get_full_history()
    return {"status":"success","intent":intent,"text":text}


def handle_switch_project(orchestrator, intent, *, target=None, raw=None):
    import os
    from datetime import datetime
    from lab_v4_dev.core.project_context import CYBERLAB_ROOT
    WORKSPACE_DIR = os.path.join(CYBERLAB_ROOT, "workspace")
    from lab_v4_dev.core.project_context import (
        BASE_PROJECT_ROOT, get_active_project, set_active_project
    )
    # استخرج المسار أو اسم المشروع من النص
    words = raw.split()
    path = BASE_PROJECT_ROOT if intent == Intent.RETURN_BASE_PROJECT else None

    if intent == Intent.SWITCH_PROJECT:
        # 1) مسار صريح
        for w in words:
            if "/" in w or w in ["~", "."]:
                path = w
                break

        # 2) اسم مشروع مسجل
        if path is None:
            from lab_v4_dev.project_registry.registry import get_project_by_name

            # target يأتي من Intent Parser عندما يذكر اسم المشروع.
            project_name = target.strip() if isinstance(target, str) else ""
            if project_name:
                project = get_project_by_name(project_name)
                if project:
                    path = project["root"]

        # 3) اسم cyberlab_agent هو المشروع الأساسي نفسه
        if path is None and "cyberlab_agent" in raw.lower():
            path = BASE_PROJECT_ROOT
    if not path:
        if intent == Intent.SWITCH_PROJECT and any(
            phrase in raw for phrase in ["مشروع اخر", "مشروع آخر", "مشروع ثاني"]
        ):
            return {
                "status": "needs_target",
                "intent": intent,
                "text": "حدد اسم المشروع الذي تريد التبديل إليه."
            }

        proj = get_active_project()
        return {"status":"success","intent":intent,
                "text": f"المشروع النشط حالياً: {proj.name} ({proj.root})"}
    previous_project = get_active_project()
    r = set_active_project(path)
    if r["status"] != "success":
        return {"status":"failed","intent":intent,"text":r["message"]}
    p = r["project"]
    # بناء فهرس المشروع الجديد تلقائياً (project_index + dependency_graph)
    try:
        from lab_v4_dev.core.project_context import project_index_dir
        import os as _os
        proj_root = r["project"]["root"]
        idx_dir = project_index_dir(proj_root)
        _os.makedirs(idx_dir, exist_ok=True)
        # اكتشاف نوع المشروع: Python أم TypeScript
        has_py = any(f.endswith(".py") for _, _, fs in _os.walk(proj_root)
                     for f in fs if "node_modules" not in _ and ".git" not in _)
        has_ts = _os.path.exists(_os.path.join(proj_root, "package.json"))
        if has_ts and not has_py:
            import sys as _sys
            _sys.path.insert(0, os.path.join(CYBERLAB_ROOT, "lab_v4_dev", "awareness"))
            from ts_reader import scan_project as _scan_ts
            snapshot = _scan_ts(proj_root)
            # نسخ مخرجات ts_reader إلى مجلد الفهرس الصحيح لهذا المشروع
            import shutil as _shutil, json as _json
            src_dir = os.path.join(WORKSPACE_DIR, "external_index")
            for fname in ["project_index.json","dependency_graph.json",
                          "project_snapshot.json"]:
                sp = _os.path.join(src_dir, fname)
                if _os.path.exists(sp):
                    _shutil.copy(sp, _os.path.join(idx_dir, fname))
            # critical_files.json لا ينتجه ts_reader، نبنيه من snapshot
            with open(_os.path.join(idx_dir,"critical_files.json"),"w",
                      encoding="utf-8") as cf:
                _json.dump({"critical": snapshot.get("critical_files",[])},
                           cf, ensure_ascii=False)
            indexed = " (تم فهرسته كـ TypeScript ✅)"
        else:
            from lab_v4_dev.awareness.project_index import save_index
            from lab_v4_dev.awareness.project_reader import ProjectReader
            reader = ProjectReader()
            reader.scan_files()
            reader.build_graph()
            reader.generate_outputs()
            save_index()
            indexed = " (تم فهرسته ✅)"
    except Exception as e:
        indexed = f" (فشل الفهرسة: {e})"
    # حفظ سجل المشاريع — عبر project_knowledge
    try:
        from lab_v4_dev.awareness.project_knowledge import get_project_history, save_project_history
        hist = get_project_history()
        if not isinstance(hist, dict):
            hist = {"last_project": None, "last_root": None, "history": []}
        entry = {"name": p["name"], "root": p["root"], "last_used": datetime.now().isoformat()[:16]}
        hist["last_project"] = p["name"]
        hist["last_root"] = p["root"]
        hist["history"] = [e for e in hist.get("history", []) if e.get("name") != p["name"]]
        hist["history"].insert(0, entry)
        hist["history"] = hist["history"][:10]
        save_project_history(hist)
    except: pass
    from lab_v4_dev.core.audit import emit_event
    emit_event("project.switched", source="orchestrator", context={"project_root": p["root"]}, details={"previous_root": previous_project.root, "new_root": p["root"], "project_name": p["name"], "index_result": indexed.strip()})
    return {"status":"success","intent":intent,
            "text": f"✅ تم التبديل إلى: {p['name']}\nالمسار: {p['root']}{indexed}"}



__all__ = ["handle_last_project", "handle_current_version", "handle_release_index", "handle_analyze_release", "handle_compare_versions", "handle_project_timeline", "handle_switch_project"]
