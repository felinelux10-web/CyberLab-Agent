
# CyberLab Agent v4.6-prep
# core/orchestrator.py
# Coordination Layer — Phase 5 (Full Control)

from datetime import datetime
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.executor.safe_pipeline import SafePipeline
from lab_v4_dev.awareness.project_memory import load_memory, save_memory
from lab_v4_dev.planner.impact_analyzer import analyze_impact
from lab_v4_dev.core.logger import log
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.context.context_resolver import bind_context
from lab_v4_dev.core.contracts import Request, Context, Response, PreparedExecutionRequest
from lab_v4_dev.llm.router import needs_llm
from lab_v4_dev.llm.gateway import ask
from lab_v4_dev.llm.prompt_builder import build_cybersec_prompt
from lab_v4_dev.awareness.knowledge_retriever import resolve_project_scope
from lab_v4_dev.config.provider_config import get_active_provider
import os
import re
_re_module = re
import shutil
import uuid
import inspect

CYBERLAB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKSPACE_DIR = os.path.join(CYBERLAB_ROOT, "workspace")

class Orchestrator:

    def __init__(self, agent, context=None):
        self.agent    = agent
        self.history  = []
        self.active   = True
        self.phase    = "5-full-control"
        self.pipeline = None

        # Canonical ContextStore is owned by Agent.
        # Fallback preserves standalone Orchestrator compatibility.
        self.context  = context if context is not None else ContextStore()
        self._analyzed_files  = set()
        self._impact_analyzed = set()
    def _get_pipeline(self):
        if not self.pipeline:
            self.pipeline = SafePipeline(self.agent.db)
        return self.pipeline

    def _submit_prepared_execution(self, intent, target=None, context=None,
                                    request_id=None, execution=None):
        loop = getattr(self.agent, "loop", None)
        if loop is None:
            return {
                "status": "failed",
                "error": "EventLoop غير متاح"
            }

        request = PreparedExecutionRequest(
            intent=intent,
            target=target,
            context=context if context is not None else Context(),
            request_id=request_id,
            metadata={"execution": execution or {}},
        )

        loop.submit_prepared(request)
        return loop.tick()

    def handle(
        self,
        request: str,
        parsed: dict | None = None,
        *,
        context_resolved: bool = False,
        conversation_history: list | None = None,
        context_transition: str | None = None,
        route_decision=None,
    ) -> dict:
        request = Request.from_input(request)
        raw_request = request.raw_text

        if route_decision is not None:
            authorized_route = str(getattr(route_decision, "route", ""))
            if authorized_route not in {"L-EXEC", "L-SESSION", "L-FACT", "P-TOOL"}:
                return {
                    "status": "denied",
                    "intent": (parsed or {}).get("intent"),
                    "source": "route_decision_handle_guard",
                    "executed": False,
                    "text": "قرار التوجيه لا يمنح Orchestrator ملكية هذا الطلب.",
                }
            parsed_intent = (parsed or {}).get("intent")
            selector_kind = str(((parsed or {}).get("session_selector") or {}).get("kind") or "none")
            saved_session_operation = (
                parsed_intent == Intent.SESSION_RESTORE
                or (
                    parsed_intent == Intent.RESUME
                    and selector_kind in {"number", "id", "latest", "previous_dialogue", "search", "list"}
                )
            )
            if saved_session_operation and authorized_route != "L-SESSION":
                return {
                    "status": "denied",
                    "intent": parsed_intent,
                    "source": "route_decision_saved_session_owner_guard",
                    "executed": False,
                    "text": "لا يسمح قرار التوجيه الحالي بقراءة جلسة محفوظة أو استعادتها.",
                }
            if authorized_route == "L-SESSION" and parsed_intent not in (Intent.SESSION_RESTORE, Intent.RESUME):
                return {
                    "status": "denied",
                    "intent": (parsed or {}).get("intent"),
                    "source": "route_decision_session_guard",
                    "executed": False,
                    "text": "الطلب لا يطابق مسار استعادة الجلسة الذي أجازه قرار التوجيه.",
                }

        if route_decision is not None and authorized_route == "L-SESSION":
            output_kind = str(getattr(route_decision, "output_kind", "none") or "none")
            evidence_scope = str(getattr(route_decision, "evidence_scope", "none") or "none")
            session_ref = getattr(route_decision, "session_ref", None)
            selector_kind = str(((parsed or {}).get("session_selector") or {}).get("kind") or "none")
            if output_kind in {
                "summary", "brief", "report", "topic_summary", "transcript",
                "continue_topic",
            }:
                valid_scope = (
                    evidence_scope == "saved_session" and session_ref is not None
                ) or (
                    evidence_scope == "saved_sessions"
                    and selector_kind == "list"
                    and session_ref is None
                )
                if not valid_scope:
                    return {
                        "status": "denied",
                        "intent": (parsed or {}).get("intent"),
                        "source": "route_decision_evidence_scope_guard",
                        "executed": False,
                        "text": "قرار التوجيه لا يحدد نطاق أدلة محفوظًا صالحًا لهذا المخرج.",
                    }

        # DNI-10: task chains are executable work and may run only when the
        # immutable route explicitly grants execution ownership.
        from lab_v4_dev.core.task_chain import is_chain, detect_chain, execute_chain
        if (route_decision is None or getattr(route_decision, "route", None) == "L-EXEC") and is_chain(raw_request):
            steps = detect_chain(raw_request)
            if len(steps) > 1:
                return execute_chain(steps, self)

        timestamp = datetime.now().isoformat()

        # Intent authority:
        # ConversationManager may already have resolved the request.
        # Never resolve the same request a second time.
        if parsed is None:
            parsed = parse(raw_request)

        intent    = parsed.get("intent")
        target    = parsed.get("target", "")
        ctx_hint  = parsed.get("context", "general")

        entry = {
            "timestamp": timestamp,
            "request"  : request,
            "intent"   : intent,
            "target"   : target,
            "context"  : ctx_hint,
            "status"   : "pending",
        }

        # INTENT REBUILD — PATCH 01
        #
        # parse() is the canonical Intent resolution boundary.
        #
        # Context binding may supply execution data for explicit result/repeat
        # operations, but it must not replace a subject authorized by the
        # ConversationManager or inject one into an ambiguous dialogue turn.
        #
        # Semantic Router remains available for compatibility elsewhere,
        # but it is not permitted to re-classify this request here.

        operational_context = Context.from_store(self.context)
        bound = bind_context(intent, raw_request, self.context)
        if context_resolved and bound.get("injected"):
            bound = {}

        if bound.get("target") and not target:
            target = bound["target"]
        # ─── Pre-handler Policy ───
        blocked = self._pre_handler_policy(intent, target, raw_request)
        if blocked:
            return blocked
        # ─── Runtime Execution (Series 9) ───
        _rt = getattr(self.agent, "runtime", None)
        if _rt:
            try:
                _rt.start(
                    operation=intent,
                    project="cyberlab_agent",
                    goal=intent,
                    phase="execution"
                )
                _rt.update_active_file(target)
            except:
                pass
        response_attributes = parsed.get("response_attributes") or {}
        route_kwargs = {}
        route_parameters = inspect.signature(self._route).parameters
        if response_attributes and "response_attributes" in route_parameters:
            route_kwargs["response_attributes"] = response_attributes
        if "conversation_history" in route_parameters:
            route_kwargs["conversation_history"] = conversation_history
        if "context_transition" in route_parameters:
            route_kwargs["context_transition"] = context_transition
        if "session_selector" in route_parameters:
            route_kwargs["session_selector"] = parsed.get("session_selector")
        if "route_decision" in route_parameters:
            route_kwargs["route_decision"] = route_decision
        result = self._route(intent, target, ctx_hint, raw_request, **route_kwargs)
        if _rt:
            try:
                _rt.end({
                    "intent": intent,
                    "status": result.get("status")
                })
            except:
                pass
        # ─── Apply Profile ───
        result = self._apply_profile(result, intent)

        # v5.3.1 — إضافة تحذير تلقائي حسب مستوى الخطورة
        from lab_v4_dev.intent.risk_levels import get_warning
        warning = get_warning(intent)
        if warning and isinstance(result, dict):
            result["warning"] = warning

        entry["status"] = result.get("status", "unknown")
        # لا تحدث السياق عند show_last_result
        read_only_session_report = (
            isinstance(result, dict)
            and result.get("context_action") == "read_only_report"
        )
        if intent != "show_last_result" and not read_only_session_report:
            self.context.update(intent, target, result)
        self.history.append(entry)

        log.debug(f"Orch[{self.phase}]: {intent} → {entry['status']}")
        return result

    def _pre_handler_policy(self, intent, target, raw) -> dict | None:
        """طبقة البصمة — قبل التنفيذ. ترجع dict إذا يجب الإيقاف، أو None إذا مسموح."""
        try:
            from lab_v4_dev.user_data.profile_loader import load_profile
            p = load_profile()
        except:
            return None
        eng  = p.get("engineering_style", {})
        mem  = p.get("memory_policy", {})
        trust= p.get("trust_policy", {})

        # analyze_before_modify
        if intent in ("modify_code","modify_file") and eng.get("analyze_before_modify", False):
            if target and target not in getattr(self, "_analyzed_files", set()):
                return {"status":"blocked","intent":intent,
                        "text": "❌ يجب تحليل الملف اولاً قبل التعديل. استخدم: حلل ملف " + str(target)}

        # require_impact_analysis — يشغّل التحليل تلقائياً بدل المنع
        if intent in ("modify_code","repair_approve") and eng.get("require_impact_analysis", False):
            if target and target not in getattr(self, "_impact_analyzed", set()):
                try:
                    from lab_v4_dev.awareness.dependency_map import get_impact
                    get_impact(target)
                    self._impact_analyzed.add(target)
                except:
                    pass

        # allow_guessing = false
        if not trust.get("allow_guessing", True):
            if intent in ("self_diagnose","full_diagnose","repair_analyze"):
                pass  # هذه لها مصادر حقيقية — مسموح

        return None

    def _apply_profile(self, result: dict, intent: str) -> dict:
        """طبقة البصمة — بعد التنفيذ. تعدل شكل النتيجة فقط."""
        try:
            from lab_v4_dev.user_data.profile_loader import load_profile
            p = load_profile()
        except:
            return result
        eng = p.get("engineering_style", {})

        # تذكير Smoke Test
        if intent in ("modify_code","generate_code","repair_approve"):
            if eng.get("smoke_test_required", False):
                result["profile_reminder"] = "🧪 تذكير: Smoke Test مطلوب حسب سياسة المستخدم."

        # تذكير versioning
        if intent in ("modify_code","repair_approve"):
            if eng.get("versioning_required", False):
                current = result.get("profile_reminder","")
                result["profile_reminder"] = current + "\n📦 تذكير: احفظ إصداراً جديداً بعد التعديل."

        return result

    def _route(
        self,
        intent,
        target,
        context,
        raw,
        *,
        response_attributes: dict | None = None,
        conversation_history: list | None = None,
        context_transition: str | None = None,
        session_selector: dict | None = None,
        route_decision=None,
    ) -> dict:
        if route_decision is not None:
            authorized_route = str(getattr(route_decision, "route", ""))
            if authorized_route not in {"L-EXEC", "L-SESSION", "L-FACT", "P-TOOL"}:
                return {
                    "status": "denied", "intent": intent,
                    "source": "route_decision_orchestrator_guard",
                    "executed": False,
                    "text": "قرار التوجيه لا يمنح Orchestrator ملكية هذا الطلب.",
                }
            if authorized_route == "L-SESSION" and intent not in (Intent.SESSION_RESTORE, Intent.RESUME):
                return {
                    "status": "denied", "intent": intent,
                    "source": "route_decision_session_guard",
                    "executed": False,
                    "text": "قرار التوجيه يحدد مسار جلسة محفوظة لكن النية لا تطابق الاستعادة.",
                }

        def authorized_ask(*args, **kwargs):
            if route_decision is not None and not bool(
                getattr(route_decision, "provider_allowed", False)
            ):
                return {
                    "status": "unavailable",
                    "message": "provider denied by RouteDecision",
                }
            return ask(*args, **kwargs)

        # ─── Response Cache ───
        from lab_v4_dev.intent.response_cache import get as rcache_get
        _cache_intents = ["analyze_code","project_scan","cyber_explain","health","self_diagnose"]
        if intent in _cache_intents and not response_attributes:
            # لا نستخدم cache عندما يتطلب الشرح/التحليل موضوعًا ولا يوجد target.
            # يمنع إعادة إجابة قديمة عن موضوع لم يحدده المستخدم.
            _skip_cache = (
                intent in {"analyze_code", "cyber_explain"}
                and not target
            )
            if not _skip_cache:
                cached = rcache_get(str(intent), target or "")
                if cached:
                    return {"status":"success","intent":intent,"source":"cache","text":cached}

        # Registered handlers run only after the legacy response-cache gate.
        from lab_v4_dev.core.orchestrator_handlers.dispatch import dispatch as _dispatch_handler
        _handled = _dispatch_handler(
            self, intent, target=target, raw=raw, authorized_ask=authorized_ask,
            route_decision=route_decision, session_selector=session_selector,
            response_attributes=response_attributes,
            conversation_history=conversation_history,
            context_transition=context_transition,
        )
        if _handled is not None:
            return _handled

        # ─── التغييرات ───
        if intent == Intent.SHOW_CHANGES:
            tasks = self.agent.memory.recent_tasks(10)
            lines = ["آخر التعديلات:"]
            for t in tasks:
                icon = "✅" if t["status"] == "success" else "❌"
                lines.append(f"  {icon} {t['intent'][:40]}")
            return {
                "status": "success",
                "intent": intent,
                "text"  : chr(10).join(lines),
                "tasks" : [{"intent": t["intent"][:40],
                            "status": t["status"]} for t in tasks],
            }

        # ─── تنظيف عام: لا تفترض الجهاز عند غياب الهدف ───
        elif intent == Intent.CLEAN:
            return {
                "status": "needs_clarification",
                "intent": intent,
                "text": "ما الذي تريد تنظيفه؟ حدّد الهدف قبل المتابعة.",
            }

        # ─── تنظيف الجهاز: لا يصل إليه إلا action + device target ───
        elif intent == Intent.CLEAN_DEVICE:
            from lab_v4_dev.core.cleaner import run_full_clean
            result = run_full_clean()
            lines = ["=== تنظيف الهاتف ==="]
            lines.append(f"📦 المساحة قبل : {result['before_mb']} MB")
            lines.append(f"📦 المساحة بعد : {result['after_mb']} MB")
            lines.append(f"🗑️ تم تحرير   : {result['freed_mb']} MB ({result['freed_kb']} KB)")
            lines.append("─── التفاصيل ───")
            for d in result["details"]:
                lines.append(f"  {d['type']}: حذف {d['removed']} عنصر — {d['size_kb']} KB")
            return {"status":"success","intent":intent,"text":chr(10).join(lines)}

        # ─── تنظيف الكود: خطة مراجعة فقط، دون تعديل تلقائي ───
        elif intent == Intent.CLEANUP_CODE:
            from lab_v4_dev.planner.planner import Planner

            scope = str(target or "").strip()
            plan = Planner().from_actions(
                {
                    "action": getattr(intent, "value", intent),
                    "target": scope or None,
                },
                [
                    {
                        "step_id": "step-1",
                        "action": "confirm_scope",
                        "parameters": {"target": scope or None},
                        "description": "تأكيد ملف/مجلد ونطاق التنظيف المطلوب",
                    },
                    {
                        "step_id": "step-2",
                        "action": "prepare_reviewable_proposal",
                        "parameters": {
                            "target": scope or None,
                            "requires_user_review": True,
                        },
                        "depends_on": ["step-1"],
                        "description": "إعداد مقترح قابل للمراجعة دون تطبيقه",
                    },
                ],
                plan_id=f"cleanup-code-{uuid.uuid4().hex}",
                metadata={
                    "execution_status": "not_started",
                    "mutates_files": False,
                    "user_review_required": True,
                },
            )
            if scope:
                message = (
                    f"أعددت خطة مراجعة مبدئية للنطاق {scope}. هذه خطة فقط؛ "
                    "لم يُعدّل أو يُحذف أي ملف. حدّد قواعد التنظيف المطلوبة "
                    "أو اطلب مراجعة النطاق للمتابعة."
                )
            else:
                message = (
                    "تنظيف الكود يتطلب تحديد مسار ملف/مجلد أو نطاق واضح قبل إعداد "
                    "مقترح قابل للمراجعة. الخطة المرفقة مبدئية فقط؛ لم يُعدّل "
                    "أو يُحذف أي ملف."
                )
            return {
                "status": "needs_clarification",
                "intent": intent,
                "target": scope or "",
                "text": message,
                "plan": plan.to_dict(),
                "plan_only": True,
                "executed": False,
            }

        # ─── Plan Change (PIE) ───
        elif intent == Intent.PLAN_CHANGE:
            import re as _re_pie
            m = _re_pie.search(r'[\w./]+\.py', raw)
            if not m:
                return {"status":"needs_clarification","intent":intent,
                        "text":"أي ملف تريد تخطيط تعديله؟ مثال: خطط لتعديل core/agent.py"}
            target_file = m.group(0)
            try:
                from lab_v4_dev.project_knowledge.analysis_engine import AnalysisEngine
                from lab_v4_dev.dni.knowledge_router import create_p10_plan_from_change

                engine = AnalysisEngine()
                if os.path.exists(target_file):
                    engine.analyze_file(target_file)

                plan = create_p10_plan_from_change(
                    target_file,
                    plan_id=f"pie-{target_file}",
                    metadata={"source": "orchestrator.plan_change"},
                )

                impacted = [
                    step.parameters.get("file")
                    for step in plan.steps
                    if step.parameters.get("file")
                ]
                exec_plan = plan.steps
                lines = ["خطة تعديل " + target_file + ":"]
                if impacted:
                    lines.append("الملفات المتأثرة (" + str(len(impacted)) + "):")
                    for f2 in impacted[:5]:
                        lines.append("  ⚠️  " + f2)
                else:
                    lines.append("✅ لا توجد ملفات متأثرة مباشرة")
                if exec_plan:
                    lines.append("خطوات التنفيذ (" + str(len(exec_plan)) + "):")
                    for index, step in enumerate(exec_plan[:3], start=1):
                        file_path = step.parameters.get("file", "")
                        priority = step.parameters.get("priority", "")
                        lines.append(
                            "  [" + str(index) + "] "
                            + file_path
                            + " — "
                            + step.action
                            + " (" + priority + ")"
                        )
                lines.append("ℹ️ هذه خطة معاينة فقط — لا يتم أي تعديل حتى الآن.")
                return {"status":"success","intent":intent,"source":"pie",
                        "text":"\n".join(lines)}
            except Exception as _e_pie:
                return {"status":"failed","intent":intent,
                        "text":"خطأ في PIE: " + str(_e_pie)}

        # ─── Self Diagnostics ───
        elif intent in [Intent.SELF_DIAGNOSE, Intent.FULL_DIAGNOSE]:
            from lab_v4_dev.monitor.self_diagnostics import (
                run_diagnostics, format_quick, format_full
            )
            quick  = (intent == Intent.SELF_DIAGNOSE)
            result = run_diagnostics(quick=quick)
            text   = format_quick(result) if quick else format_full(result, self.context)
            return {
                "status": "success",
                "intent": intent,
                "text"  : text,
                "health": result["health"],
            }

        # ─── Read External Project (v5.9) ───
        elif intent == Intent.READ_EXTERNAL_PROJECT:
            import re as _re, sys
            m = _re.search(r'(~/\S+|/\S+)', raw)
            if m:
                path = os.path.expanduser(m.group(1))
            else:
                path = os.path.expanduser("~/external_projects/dynamic-lab-app")
            if not os.path.exists(path):
                return {"status":"success","intent":intent,
                        "text":f"المسار غير موجود: {path}"}
            from lab_v4_dev.core.project_context import set_active_project, get_active_project
            previous_project = get_active_project()
            switched = set_active_project(path)
            if switched["status"] != "success":
                return {"status":"failed","intent":intent,"text":switched["message"]}
            from lab_v4_dev.awareness.ts_reader import scan_project
            snapshot = scan_project(path)
            from lab_v4_dev.core.audit import emit_event
            emit_event("project.switched", source="orchestrator", context={"project_root": path}, details={"previous_root": previous_project.root, "new_root": path, "reason": "read_external_project"})
            emit_event("project.external_scan", source="orchestrator", context={"project_root": path}, details={"project_type": snapshot.get("project_type"), "total_files": snapshot.get("total_files"), "entry_points": snapshot.get("entry_points", []), "critical_files": snapshot.get("critical_files", [])[:10]})
            lines = [f"تم قراءة المشروع: {path}"]
            lines.append(f"النوع: {snapshot['project_type']}")
            lines.append(f"الملفات: {snapshot['total_files']}")
            lines.append(f"نقاط الدخول: {', '.join(snapshot['entry_points'])}")
            lines.append(f"أهم الملفات:")
            for f in snapshot['critical_files'][:5]:
                lines.append(f"  🔴 {f}")
            return {"status":"success","intent":intent,
                    "text":"\n".join(lines)}

        # ─── Explicit provider fallback (preserved after registered handlers) ───
        elif needs_llm(intent):
            from lab_v4_dev.llm.prompt_builder import build_project_context
            system = build_project_context(
                question=raw,
                intent=intent,
                project_scope=resolve_project_scope(raw, intent=intent),
            )
            result = authorized_ask(raw, system=system, max_tokens=300)
            return {
                "status": result["status"],
                "intent": intent,
                "source": result.get("provider_used", get_active_provider()),
                "route": result.get("provider_used", get_active_provider()),
                "text": result.get("text", result.get("message", "")),
                "tokens": result.get("tokens", 0),
            }

        # ─── Code Engine ───
        elif intent == Intent.GENERATE_CODE:
            from lab_v4_dev.core.code_engine import generate_code
            # نمرر raw دائماً لأنه يحتوي الوصف الكامل
            result = generate_code(raw)
            if result["status"] != "success":
                return {"status":"failed","intent":intent,
                        "text":"فشل في كتابة الكود"}
            self.context.current_file = result["saved_to"]
            self.context.current_subject = f"كتابة سكريبت: {raw[:60]}"
            return {
                "status"     : "success",
                "intent"     : intent,
                "text"       : result["explanation"][:600],
                "code"       : result["code"],
                "saved_to"   : result["saved_to"],
            }

        elif intent == Intent.ANALYZE_CODE:
            from lab_v4_dev.core.code_engine import analyze_code
            code_text = self.context.last_result.get("code","") if self.context.last_result else ""
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
                self._analyzed_files.add(target)
            # ─── حفظ الموضوع في السياق ───
            if text and result.get("status") == "success":
                self.context.current_subject = raw
            return {
                "status" : result.get("status","success"),
                "intent" : intent,
                "source" : result.get("provider_used", get_active_provider()),
                "text"   : text,
            }

        elif intent == Intent.MODIFY_CODE:
            from lab_v4_dev.core.symbol_resolver import resolve as sym_resolve
            from lab_v4_dev.core.surgical_editor import extract_symbol, patch_symbol
            from lab_v4_dev.core.code_engine import modify_code

            words = raw.strip().split()
            if len(words) < 2:
                return {"status":"needs_target","intent":intent,
                        "text":"\u0645\u0627\u0630\u0627 \u062a\u0631\u064a\u062f \u0623\u0646 \u0623\u0639\u062f\u0644\u061f"}

            # Use the execution context only when this request omits a target.
            context_file = getattr(self.context, "current_file", None)
            if context_file and not os.path.isfile(os.path.expanduser(str(context_file))):
                context_file = ""
            target_path = target or context_file or ""
            resolved = sym_resolve(raw, target_path)
            if resolved.get("ambiguous"):
                candidates = [item.get("file", "") for item in resolved.get("candidates", [])]
                return {"status": "needs_clarification", "intent": intent,
                        "text": "وجدت أكثر من ملف مرشح. حدّد الملف: " + "، ".join(candidates[:5]),
                        "candidates": candidates}
            if not resolved["found"]:
                return {"status":"needs_target","intent":intent,
                        "text":"\u0644\u0645 \u0623\u062c\u062f \u0627\u0644\u0645\u0644\u0641 \u0623\u0648 \u0627\u0644\u062f\u0627\u0644\u0629"}

            fp = resolved["file"]
            symbol = resolved["symbol"]

            if symbol:
                sym_data = extract_symbol(fp, symbol)
                code_text = sym_data.get("code", "")
                is_surgical = bool(code_text)
            else:
                try:
                    code_text = open(fp, encoding="utf-8", errors="ignore").read()
                except:
                    return {"status":"failed","intent":intent,"text":"\u0644\u0627 \u064a\u0645\u0643\u0646 \u0642\u0631\u0627\u0621\u0629 \u0627\u0644\u0645\u0644\u0641"}
                is_surgical = False

            if not code_text:
                return {"status":"failed","intent":intent,"text":"\u0644\u0627 \u064a\u0648\u062c\u062f \u0643\u0648\u062f"}

            result = modify_code(code_text, raw)
            if result["status"] != "success" or not result.get("code"):
                return {"status":result["status"],"intent":intent,
                        "text":result.get("text",result.get("explanation",""))}

            with open(fp, encoding="utf-8") as _vf:
                _orig_source = _vf.read()

            if is_surgical:
                from lab_v4_dev.core.surgical_editor import clean_llm_output
                clean_code = clean_llm_output(result["code"], symbol)
                final_code = patch_symbol(_orig_source, symbol,
                                          clean_code,
                                          sym_data["start_line"],
                                          sym_data["end_line"])
            else:
                final_code = result["code"]

            # تحقق من صحة الـ patch بعد الدمج
            from lab_v4_dev.core.surgical_editor import validate_patch
            _vcheck = validate_patch(_orig_source, final_code)
            if not _vcheck["ok"]:
                return {"status":"failed","intent":intent,
                        "text":"\u274c \u063a\u064a\u0631 \u0622\u0645\u0646: " + str(_vcheck)}

            if final_code == _orig_source:
                return {"status":"failed","intent":intent,
                        "text":"لم ينتج التعديل أي تغيير في الملف"}

            try:
                _db = self.agent.db
                if _db is not None and getattr(_db, "conn", None) is None:
                    _db.connect()
                pipeline = self.pipeline or SafePipeline(_db)
                plan = {"files": [fp], "reason": raw}
                pipe_result = pipeline.execute(plan, {fp: final_code})
                mode = "surgical" if is_surgical else "full"
                if pipe_result.get("status") == "success":
                    if not os.path.isfile(fp):
                        return {"status":"failed","intent":intent,
                                "text":"فشل التحقق: الملف غير موجود بعد الكتابة"}
                    with open(fp, encoding="utf-8") as _after_file:
                        _after_source = _after_file.read()
                    if _after_source != final_code:
                        return {"status":"failed","intent":intent,
                                "text":"فشل التحقق: المحتوى المكتوب لا يطابق التعديل"}
                    self.context.current_file = fp
                    return {"status":"success","intent":intent,
                            "text":"\u2705 [" + mode + "] " + (symbol or fp.split("/")[-1]),
                            "file": fp, "verified": True}
                else:
                    return {"status":"failed","intent":intent,
                            "text":"\u274c " + str(pipe_result.get("reason",""))}
            except Exception as e:
                return {"status":"failed","intent":intent,"text":str(e)}

        # ─── Sandbox Executor ───
        elif intent == Intent.RUN_SCRIPT:
            from lab_v4_dev.core.sandbox_executor import run_code

            # استخرج اسم الملف
            scripts_dir = os.path.join(WORKSPACE_DIR, "scripts")
            scripts = sorted(
                [f for f in os.listdir(scripts_dir) if f.endswith(".py")],
                key=lambda x: os.path.getmtime(os.path.join(scripts_dir, x)),
                reverse=True
            ) if os.path.exists(scripts_dir) else []
            if not scripts:
                return {"status":"failed","intent":intent,"text":"لا توجد سكريبتات محفوظة"}
            # إذا ذكر اسم محدد استخدمه
            target_script = None
            for s in scripts:
                if s in raw:
                    target_script = os.path.join(WORKSPACE_DIR, "scripts", s)
                    break
            # استخدم آخر سكريبت تم كتابته في هذه الجلسة
            if not target_script and self.context.last_result:
                saved = self.context.last_result.get("saved_to","")
                if saved and os.path.exists(saved):
                    target_script = saved
            # آخر ملف في المجلد
            if not target_script:
                target_script = os.path.join(WORKSPACE_DIR, "scripts", scripts[0])
            r = run_code(target_script, timeout=10)
            if r["status"] == "success":
                meta = f"⏱ {r.get('duration','?')}s | exit: {r.get('exit_code',0)}"
                return {
                    "status": "success", "intent": intent,
                    "text"  : f"✅ {target_script}\n{meta}\n\n{r.get('output','لا يوجد output')}",
                }
            else:
                meta = f"⏱ {r.get('duration','?')}s | exit: {r.get('exit_code','?')}"
                return {
                    "status": "error", "intent": intent,
                    "text"  : f"❌ {target_script}\n{meta}\n{r.get('error','')}\nتقرير: {r.get('report','')}",
                }

        # ─── Repair Engine ───
        elif intent == Intent.REPAIR_ANALYZE:
            from lab_v4_dev.core.repair.error_reader import get_latest_error
            from lab_v4_dev.core.repair.error_analyzer import analyze
            from lab_v4_dev.core.repair.fix_generator import generate_fix
            from lab_v4_dev.core.repair.diff_approval import show_fix_proposal, save_pending_fix
            error = get_latest_error()
            if not error or not error.get("message"):
                return {"status":"success","intent":intent,
                        "text":"لا توجد أخطاء مسجلة ✅"}
            analysis = analyze(error)
            if not analysis.get("fixable", False):
                return {"status":"success","intent":intent,
                        "text":f"الخطأ: {error.get('message','')}\nيحتاج مراجعة يدوية"}
            fix      = generate_fix(error, analysis)
            proposal = show_fix_proposal(fix, error)
            path     = save_pending_fix(error.get("file",""), fix, error, analysis)
            self.context.last_result = {"pending_path": path, "fix": fix}
            return {"status":"success","intent":intent,"text":proposal}

        elif intent == Intent.REPAIR_APPROVE:
            from lab_v4_dev.core.repair.diff_approval import apply_fix, list_pending
            last = self.context.last_result or {}
            pending_path = last.get("pending_path","")
            if not pending_path:
                pending = list_pending()
                if pending:
        
                    pending_path = os.path.join("workspace/pending_fixes", pending[0]["file"])
            if not pending_path:
                return {"status":"failed","intent":intent,
                        "text":"لا يوجد إصلاح معلق"}
            result = apply_fix(pending_path, approved=True)
            return {"status":result["status"],"intent":intent,
                    "text":f"{'✅' if result['status']=='success' else '❌'} {result['message']}"}

        elif intent == Intent.REPAIR_REJECT:
            self.context.last_result = None
            return {"status":"success","intent":intent,
                    "text":"تم رفض الإصلاح — لم يتم تعديل أي شيء"}

        elif intent == Intent.PENDING_FIXES:
            from lab_v4_dev.core.repair.diff_approval import list_pending
            pending = list_pending()
            if not pending:
                return {"status":"success","intent":intent,
                        "text":"لا توجد إصلاحات معلقة ✅"}
            lines = ["=== الإصلاحات المعلقة ==="]
            for p in pending:
                lines.append(f"⏳ {p['fix']}")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── Delete File ───
        elif intent == Intent.DELETE_FILE:
            try:
                from lab_v4_dev.core.safe_io import safe_delete

                target_path = target or self.context.current_file

                if not target_path:
                    return {
                        "status": "failed",
                        "intent": intent,
                        "message": "لم يتم تحديد الملف"
                    }

                result = safe_delete(target_path, "user request")

                succeeded = result.get("status") == "success"
                if succeeded:
                    text = f"تم حذف {target_path}"
                    if result.get("audit_warning"):
                        text += "، لكن تعذرت كتابة سجل التدقيق"
                else:
                    text = result.get("message") or f"لم يتم حذف {target_path}"
                return {
                    "status": result.get("status"),
                    "intent": intent,
                    "text": text,
                    "backup": result.get("backup"),
                    "snapshot": result.get("snapshot"),
                    "audit_warning": result.get("audit_warning"),
                }

            except Exception as e:
                return {
                    "status": "failed",
                    "intent": intent,
                    "message": str(e)
                }

        # ─── fallback ───
        else:
            return {
                "status"  : "unsupported",
                "intent"  : intent,
                "message" : f"لم أفهم الأمر: {raw[:50]}",
                "executed": False,
            }

    def get_last(self)    -> dict: return self.history[-1] if self.history else {}
    def get_history(self) -> list: return self.history

    def summary(self) -> dict:
        intents = {}
        statuses = {}
        for h in self.history:
            i = h.get("intent", "?")
            s = h.get("status", "?")
            intents[i] = intents.get(i, 0) + 1
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total": len(self.history),
            "phase": self.phase,
            "intents": intents,
            "statuses": statuses,
        }

