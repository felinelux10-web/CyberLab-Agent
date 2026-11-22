
# CyberLab Agent v4.6-prep
# core/orchestrator.py
# Coordination Layer — Phase 5 (Full Control)

from datetime import datetime
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.executor.safe_pipeline import SafePipeline
from lab_v4_dev.core.logger import log
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.context.context_resolver import bind_context
from lab_v4_dev.core.contracts import Request, Context, PreparedExecutionRequest
from lab_v4_dev.llm import gateway as _gateway
import os

# Stable module-level compatibility seam. The actual gateway is resolved at
# call time so integrations may instrument it without bypassing route grants.
def ask(*args, **kwargs):
    return _gateway.ask(*args, **kwargs)


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
                                    request_id=None, execution=None,
                                    route_decision=None):
        if (
            route_decision is None
            or getattr(route_decision, "route", None) != "L-EXEC"
            or getattr(route_decision, "evidence_scope", None) != "work_state"
        ):
            return {
                "status": "denied",
                "source": "prepared_execution_route_guard",
                "executed": False,
                "text": "لا يمكن تسليم تنفيذ مجهز دون قرار L-EXEC ونطاق أدلة work_state.",
            }

        def intent_value(value):
            return str(getattr(value, "value", value) or "").casefold()

        if intent_value(intent) != intent_value(getattr(route_decision, "intent", None)):
            return {
                "status": "denied",
                "source": "prepared_execution_intent_guard",
                "executed": False,
                "text": "نية التنفيذ المجهزة لا تطابق النية التي أجازها قرار التوجيه.",
            }

        loop = getattr(self.agent, "loop", None)
        if loop is None:
            return {
                "status": "failed",
                "source": "prepared_execution_loop_unavailable",
                "executed": False,
                "text": "EventLoop غير متاح.",
            }

        try:
            request = PreparedExecutionRequest(
                intent=intent,
                route_decision=route_decision,
                target=target,
                context=context if context is not None else Context(),
                request_id=request_id,
                metadata={"execution": execution or {}},
            )
            loop.submit_prepared(request)
        except (TypeError, ValueError, PermissionError) as exc:
            return {
                "status": "denied",
                "source": "prepared_execution_contract",
                "executed": False,
                "text": str(exc),
            }
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
            if authorized_route not in {"L-EXEC", "L-SESSION", "P-TOOL"}:
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
            if authorized_route == "L-SESSION" and evidence_scope not in {
                "none", "saved_session", "saved_sessions",
            }:
                return {
                    "status": "denied", "intent": parsed_intent,
                    "source": "route_decision_session_evidence_guard",
                    "executed": False,
                    "text": "مسار الجلسات لا يسمح بقراءة أدلة خارج نطاق الجلسات المحفوظة.",
                }
            if authorized_route in {"L-EXEC", "P-TOOL"} and evidence_scope in {
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
                "continue_topic", "session_number", "session_identity",
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

        # Route explicitly prepared execution payloads through EventLoop.
        # Legacy handler dispatch remains available for operations that have
        # not yet been migrated to the prepared action/parameters contract.
        prepared_execution = (parsed or {}).get("prepared_execution")
        if (
            authorized_route == "L-EXEC"
            and isinstance(prepared_execution, dict)
        ):
            prepared_result = self._submit_prepared_execution(
                intent=intent if "intent" in locals() else (parsed or {}).get("intent"),
                target=(parsed or {}).get("target"),
                context=Context.from_store(self.context),
                request_id=request.request_id,
                execution=prepared_execution,
                route_decision=route_decision,
            )
            if isinstance(prepared_result, dict):
                prepared_result.setdefault("source", "event_loop_prepared")
                prepared_result.setdefault("executed", prepared_result.get("status") == "executed")
            self.history.append({
                "timestamp": datetime.now().isoformat(),
                "request": raw_request,
                "intent": (parsed or {}).get("intent"),
                "target": (parsed or {}).get("target", ""),
                "context": "prepared_execution",
                "status": (prepared_result or {}).get("status", "failed"),
            })
            return prepared_result

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
        from lab_v4_dev.core.orchestrator_handlers.policy import pre_handler_policy
        blocked = pre_handler_policy(self, intent, target, raw_request)
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
        from lab_v4_dev.core.orchestrator_handlers.dispatch import route_request
        result = route_request(
            self,
            intent,
            target,
            raw_request,
            response_attributes=response_attributes,
            conversation_history=conversation_history,
            context_transition=context_transition,
            session_selector=parsed.get("session_selector"),
            route_decision=route_decision,
            ask_provider=ask,
        )
        if _rt:
            try:
                _rt.end({
                    "intent": intent,
                    "status": result.get("status")
                })
            except:
                pass
        # ─── Apply Profile ───
        from lab_v4_dev.core.orchestrator_handlers.policy import apply_profile
        result = apply_profile(result, intent)

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

