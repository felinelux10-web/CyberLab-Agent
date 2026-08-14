# CyberLab Agent v4.6-prep
# core/orchestrator.py
# Coordination Layer — Phase 5 (Full Control)

from datetime import datetime
from lab_v4.intent.intent_parser import parse
from lab_v4.intent.intents import Intent
from lab_v4.executor.safe_pipeline import SafePipeline
from lab_v4.awareness.project_memory import load_memory, save_memory
from lab_v4.planner.impact_analyzer import analyze_impact
from lab_v4.core.logger import log
from lab_v4.context.context_store import ContextStore
from lab_v4.context.context_resolver import bind_context
from lab_v4.llm.router import route as llm_route, needs_llm
from lab_v4.llm.groq_client import ask
import os
import shutil

class Orchestrator:

    def __init__(self, agent):
        self.agent    = agent
        self.history  = []
        self.active   = True
        self.phase    = "5-full-control"
        self.pipeline = None
        self.context  = ContextStore()

    def _get_pipeline(self):
        if not self.pipeline:
            self.pipeline = SafePipeline(self.agent.db)
        return self.pipeline

    def handle(self, request: str) -> dict:
        timestamp = datetime.now().isoformat()
        parsed    = parse(request)
        intent    = parsed["intent"]
        target    = parsed["target"]
        ctx_hint  = parsed["context"]

        entry = {
            "timestamp": timestamp,
            "request"  : request,
            "intent"   : intent,
            "target"   : target,
            "context"  : ctx_hint,
            "status"   : "pending",
        }

        bound  = bind_context(intent, request, self.context)
        intent = bound["intent"]
        if bound.get("target"):
            target = bound["target"]
        result = self._route(intent, target, ctx_hint, request)
        entry["status"] = result.get("status", "unknown")
        # لا تحدث السياق عند show_last_result
        if intent != "show_last_result":
            self.context.update(intent, target, result)
        self.history.append(entry)

        log.debug(f"Orch[{self.phase}]: {intent} → {entry['status']}")
        return result

    def _route(self, intent, target, context, raw) -> dict:

        # ─── قراءة ───
        if intent == Intent.READ_FILE:
            if not target:
                return {"status": "needs_target", "message": "أي ملف؟"}
            try:
                text = open(target).read()
                return {"status": "success", "intent": intent,
                        "output": text[:600], "file": target}
            except FileNotFoundError:
                return {"status": "failed", "message": f"غير موجود: {target}"}

        # ─── فحص المشروع — يذهب لـ Groq ───
        elif intent == Intent.PROJECT_SCAN:
            memory = load_memory()
            total  = memory.get("total_files", 0)
            critical = [c["file"] for c in memory.get("critical_files",[])]
            context = f"المشروع يحتوي {total} ملف. الملفات الحرجة: {', '.join(critical[:3])}"
            layers  = list(memory.get("architecture", {}).keys())
            project_desc = (
                "CyberLab Agent هو Local Autonomous Engineering Runtime. "
                f"يعمل على Android/Termux. يحتوي {total} ملف. "
                f"طبقاته: {', '.join(layers)}. "
                f"ملفاته الحرجة: {', '.join(critical[:3])}. "
                "هدفه: وكيل ذكاء اصطناعي محلي على الهاتف."
            )
            system  = "أنت مساعد هندسي. " + project_desc + " أجب بالعربية بإيجاز."
            prompt  = f"{context}\n\nسؤال المستخدم: {raw}"
            result  = ask(prompt, system=system, max_tokens=300)
            return {
                "status"      : result["status"],
                "intent"      : intent,
                "source"      : "groq",
                "text"        : result.get("text", ""),
                "total_files" : total,
                "critical"    : critical,
            }

        # ─── تحليل تأثير ───
        elif intent == Intent.IMPACT_ANALYSIS:
            if not target:
                return {"status": "needs_target", "message": "أي ملف؟"}
            impact = analyze_impact(target)
            return {"status": "success", "intent": intent, "impact": impact}

        # ─── التغييرات ───
        elif intent == Intent.SHOW_CHANGES:
            from lab_v4.memory.task_history import TaskHistory
            th    = TaskHistory(self.agent.db)
            tasks = th.recent(10)
            return {
                "status": "success",
                "intent": intent,
                "tasks" : [{"intent": t["intent"][:40],
                            "status": t["status"]} for t in tasks],
            }

        # ─── تنظيف ───
        elif intent == Intent.CLEAN:
            removed = 0
            for root, dirs, files in os.walk("lab_v4"):
                for f in files:
                    if f.endswith((".pyc", ".tmp")):
                        try:
                            os.remove(os.path.join(root, f))
                            removed += 1
                        except:
                            pass
            return {"status": "success", "intent": intent, "removed": removed}

        # ─── مساحة ───
        elif intent == Intent.SPACE:
            total, used, free = shutil.disk_usage(os.path.expanduser("~"))
            return {
                "status": "success", "intent": intent,
                "total" : f"{total//(1024**3)}GB",
                "used"  : f"{used//(1024**2)}MB",
                "free"  : f"{free//(1024**2)}MB",
            }

        # ─── حالة ───
        elif intent == Intent.STATUS:
            s = self.agent.state
            h = self.agent.session.summary()
            return {
                "status"  : "success", "intent": intent,
                "mode"    : s.mode,
                "failures": s.consecutive_failures,
                "tasks"   : h["tasks_done"],
                "errors"  : h["error_count"],
            }

        # ─── صحة النظام ───
        elif intent == Intent.HEALTH:
            from lab_v4.monitor.health_check import check_health
            h = check_health(self.agent.state)
            return {"status": "success", "intent": intent, "health": h}

        # ─── تقرير ───
        elif intent in [Intent.REPORT, Intent.SESSION_REPORT]:
            h   = self.agent.session.summary()
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            return {
                "status"  : "success", "intent": intent,
                "time"    : now,
                "session" : h,
            }

        # ─── ذاكرة المشروع ───
        elif intent == Intent.MEMORY_STATUS:
            memory = load_memory()
            return {
                "status"      : "success", "intent": intent,
                "total_files" : memory.get("total_files", 0),
                "last_updated": memory.get("last_updated", "unknown"),
            }

        # ─── تقارير المشروع ───
        elif intent in [Intent.PROGRESS_REPORT, Intent.REMAINING_WORK,
                        Intent.PROJECT_REPORT]:
            memory  = load_memory()
            total   = memory.get("total_files", 0)
            system  = f"أنت مساعد هندسي لمشروع CyberLab Agent. المشروع يحتوي {total} ملف. الإصدار v4.6. أجب بالعربية."
            result  = ask(raw, system=system, max_tokens=400)
            return {
                "status": result["status"],
                "intent": intent,
                "source": "groq",
                "text"  : result.get("text",""),
            }

        # ─── Groq للمهام المعقدة ───
        elif needs_llm(intent):
            system = "أنت مساعد هندسي متخصص في تحليل المشاريع البرمجية. أجب بإيجاز وبالعربية."
            result = ask(raw, system=system, max_tokens=300)
            return {
                "status" : result["status"],
                "intent" : intent,
                "source" : "groq",
                "route"  : "groq",
                "text"   : result.get("text", result.get("message", "")),
                "tokens" : result.get("tokens", 0),
            }

        # ─── تقرير السياق ───
        elif intent == Intent.CONTEXT_REPORT:
            import json as _json, os as _os
            try:
                with open("lab_v4/cache/project_state.json") as _f:
                    s = _json.load(_f)
            except:
                s = {}
            from lab_v4.memory.task_history import TaskHistory
            th = TaskHistory(self.agent.db)
            tasks = th.recent(10)
            releases = sorted([
                d for d in _os.listdir("releases")
                if _os.path.isdir(f"releases/{d}")
            ]) if _os.path.exists("releases") else []
            return {
                "status"  : "success",
                "intent"  : intent,
                "version" : s.get("version", "?"),
                "focus"   : s.get("current_focus", "?"),
                "phases"  : s.get("completed_phases", []),
                "releases": releases,
                "tasks"   : [{"status": t["status"],
                              "intent": t["intent"][:60]}
                             for t in tasks],
            }

        # ─── نتيجة آخر أمر ───
        elif intent == "show_last_result":
            data = self.context.last_result
            if not data:
                return {"status":"success","intent":intent,
                        "text":"لا يوجد نتيجة سابقة"}
            # عرض النتيجة السابقة
            output = data.get("text") or data.get("output") or str(data)[:300]
            return {"status":"success","intent":intent,"text":output}

        # ─── سجل المهام ───
        elif intent == Intent.HISTORY:
            from lab_v4.memory.task_history import TaskHistory
            th    = TaskHistory(self.agent.db)
            tasks = th.recent(10)
            return {
                "status": "success",
                "intent": intent,
                "tasks" : [{"status": t["status"],
                            "intent": t["intent"][:50]} for t in tasks],
            }

        # ─── fallback ───
        else:
            return {
                "status" : "fallback",
                "intent" : intent,
                "message": "legacy pipeline",
            }

    def get_last(self)    -> dict: return self.history[-1] if self.history else {}
    def get_history(self) -> list: return self.history

    def summary(self) -> dict:
        intents  = {}
        statuses = {}
        for h in self.history:
            i = h.get("intent", "?")
            s = h.get("status", "?")
            intents[i]  = intents.get(i, 0) + 1
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total"   : len(self.history),
            "phase"   : self.phase,
            "intents" : intents,
            "statuses": statuses,
        }
