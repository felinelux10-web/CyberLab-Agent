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


__all__ = ["handle_last_project", "handle_current_version", "handle_release_index", "handle_analyze_release", "handle_compare_versions", "handle_project_timeline"]
