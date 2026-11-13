"""Report and work-tracking handlers migrated from Orchestrator._route."""

import os
from datetime import datetime

def handle_session_report(orchestrator, intent, *, target=None, raw=None):
        h   = orchestrator.agent.session.summary()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return {
            "status"  : "success", "intent": intent,
            "time"    : now,
            "session" : h,
        }
    

def handle_project_reports(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    if authorized_ask is None:
        return {"status": "unavailable", "intent": intent, "source": "provider_policy", "text": "بوابة المزود المصرح بها غير متاحة لهذا المسار."}
    from lab_v4_dev.awareness.project_memory import load_memory
    from lab_v4_dev.awareness.knowledge_retriever import resolve_project_scope
    from lab_v4_dev.config.provider_config import get_active_provider
        memory  = load_memory()
        total   = memory.get("total_files", 0)
        from lab_v4_dev.llm.prompt_builder import build_project_context
        system  = build_project_context(
            question=raw,
            intent=intent,
            project_scope=resolve_project_scope(raw, intent=intent),
        )
        result = authorized_ask(raw, system=system, max_tokens=400)
        return {
            "status": result["status"],
            "intent": intent,
            "source": result.get("provider_used", get_active_provider()),
            "text"  : result.get("text",""),
        }
    
            # ─── Groq للمهام المعقدة ───
            elif needs_llm(intent):
        from lab_v4_dev.llm.prompt_builder import build_project_context
        system = build_project_context(
            question=raw,
            intent=intent,
            project_scope=resolve_project_scope(raw, intent=intent),
        )
        result = authorized_ask(raw, system=system, max_tokens=300)
        return {
            "status" : result["status"],
            "intent" : intent,
            "source" : result.get("provider_used", get_active_provider()),
            "route"  : result.get("provider_used", get_active_provider()),
            "text"   : result.get("text", result.get("message", "")),
            "tokens" : result.get("tokens", 0),
        }
    

def handle_context_report(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.core.project_context import CYBERLAB_ROOT
        from lab_v4_dev.core.project_metadata import ProjectMetadata
        _meta = ProjectMetadata()
        tasks = orchestrator.agent.memory.recent_tasks(10)
        releases_dir = os.path.join(CYBERLAB_ROOT, "releases")
        releases = sorted([
            d for d in os.listdir(releases_dir)
            if os.path.isdir(os.path.join(releases_dir, d))
        ]) if os.path.exists(releases_dir) else []
        _cur_phase = _meta.get_current_phase()
        return {
            "status"  : "success",
            "intent"  : intent,
            "version" : _meta.get_version(),
            "focus"   : _meta.get_project_name(),
            "phases"  : [_cur_phase.get("name","?")] if _cur_phase else [],
            "releases": releases,
            "tasks"   : [{"status": t["status"],
                          "intent": t["intent"][:60]}
                         for t in tasks],
        }
    

def handle_history(orchestrator, intent, *, target=None, raw=None):
        tasks = orchestrator.agent.memory.recent_tasks(10)
        return {
            "status": "success",
            "intent": intent,
            "tasks" : [{"status": t["status"],
                        "intent": t["intent"][:50]} for t in tasks],
        }
    

def handle_work_tracking(orchestrator, intent, *, target=None, raw=None):
        from lab_v4_dev.data.work_tracker import get_status, get_next_task, get_remaining
        s = get_status()
        if intent == Intent.NEXT_TASK:
            return {"status":"success","intent":intent,
                    "text": f"المهمة التالية: {get_next_task()}"}
        if intent == Intent.REMAINING_TASKS:
            remaining = get_remaining()
            text = "المتبقي:\n" + "\n".join(f"  - {t}" for t in remaining)
            return {"status":"success","intent":intent,"text":text}
        # WORK_STATUS
        lines = [
            f"الإصدار: {s['version']}",
            f"التركيز: {s['current_focus']}",
            f"مكتمل  : {', '.join(s['completed']) or 'لا شيء'}",
            f"نشط    : {', '.join(s['active']) or 'لا شيء'}",
            f"مخطط   : {', '.join(s['planned']) or 'لا شيء'}",
        ]
        if s['blocked']:
            lines.append(f"محظور  : {', '.join(s['blocked'])}")
        return {"status":"success","intent":intent,"text":"\n".join(lines)}
    
    
    

def handle_work_context(orchestrator, intent, *, target=None, raw=None):
        # Work context is a live operational ledger. Archived FINAL_REPORT
        # files belong to project knowledge/reporting and must not be
        # presented as the answer to "what were we doing?".
        lines = ["=== سجل العمل الحالي ==="]
        tasks = orchestrator.agent.memory.recent_tasks(8)
        if tasks:
            lines.append("\n📋 العمليات المسجلة فعليًا:")
            for t in tasks:
                detail = str(t.get("plan") or t.get("intent") or "").strip()
                lines.append(f"  [{t['status']}] {detail[:120]}")
        else:
            lines.append("\nلا توجد عمليات عمل مسجلة في هذه الجلسة.")
    
        # Pending repairs are live state and remain part of the ledger.
        from lab_v4_dev.core.repair.diff_approval import list_pending
        pending = list_pending()
        if pending:
            lines.append(f"\n⏳ إصلاحات معلقة ({len(pending)}):")
            for p in pending:
                lines.append(f"  - {p['fix']}")
    
        return {"status":"success","intent":intent,"text":"\n".join(lines)}
    

def handle_show_last_result(orchestrator, intent, *, target=None, raw=None):
        data = orchestrator.context.last_result
        if not data:
            return {"status":"success","intent":intent,
                    "text":"لا يوجد نتيجة سابقة"}
        # عرض النتيجة السابقة
        output = data.get("text") or data.get("output") or str(data)[:300]
        return {"status":"success","intent":intent,"text":output}
    

__all__ = ["handle_session_report", "handle_project_reports", "handle_context_report", "handle_history", "handle_work_tracking", "handle_work_context", "handle_show_last_result"]
