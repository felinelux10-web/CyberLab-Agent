
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

        if route_decision is None:
            return {
                "status": "denied",
                "intent": (parsed or {}).get("intent"),
                "source": "route_decision_required",
                "executed": False,
                "text": "لا يمكن تنفيذ طلب تشغيلي دون قرار توجيه صادر عن ConversationManager.",
            }

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
            decision_intent = getattr(route_decision, "intent", None)
            parsed_value = str(getattr(parsed_intent, "value", parsed_intent) or "").casefold()
            decision_value = str(getattr(decision_intent, "value", decision_intent) or "").casefold()
            if not parsed_value or not decision_value or parsed_value != decision_value:
                return {
                    "status": "denied",
                    "intent": parsed_intent,
                    "source": "route_decision_intent_mismatch",
                    "executed": False,
                    "text": "النية الفعلية لا تطابق النية التي أجازها قرار التوجيه.",
                }
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

            evidence_scope = str(getattr(route_decision, "evidence_scope", "none") or "none")
            if authorized_route == "L-EXEC" and evidence_scope != "work_state":
                return {
                    "status": "denied", "intent": parsed_intent,
                    "source": "route_decision_work_evidence_guard",
                    "executed": False,
                    "text": "مسار التنفيذ لا يملك نطاق الأدلة المطلوب لحالة العمل.",
                }
            if authorized_route == "L-FACT" and evidence_scope != "project_state":
                return {
                    "status": "denied", "intent": parsed_intent,
                    "source": "route_decision_project_evidence_guard",
                    "executed": False,
                    "text": "مسار الحقائق المحلية لا يملك نطاق أدلة المشروع المطلوب.",
                }
            if authorized_route == "L-SESSION" and evidence_scope not in {
                "none", "saved_session", "saved_sessions",
            }:
                return {
                    "status": "denied", "intent": parsed_intent,
                    "source": "route_decision_session_evidence_guard",
                    "executed": False,
                    "text": "مسار الجلسات لا يسمح بقراءة أدلة خارج نطاق الجلسات المحفوظة.",
                }
            if authorized_route in {"L-EXEC", "L-FACT", "P-TOOL"} and evidence_scope in {
                "saved_session", "saved_sessions", "live_exchanges",
            }:
                return {
                    "status": "denied", "intent": parsed_intent,
                    "source": "route_decision_cross_scope_guard",
                    "executed": False,
                    "text": "لا يمكن توسيع نطاق الأدلة خارج المجال الذي أجازه قرار التوجيه.",
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
        if getattr(route_decision, "route", None) == "L-EXEC" and is_chain(raw_request):
            steps = detect_chain(raw_request)
            if len(steps) > 1:
                return execute_chain(steps, self, parent_route_decision=route_decision)

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

        # ─── Explicit provider fallback (preserved after registered handlers) ───
        if needs_llm(intent):
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

