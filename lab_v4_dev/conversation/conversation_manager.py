from __future__ import annotations

from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.conversation.assistant_style import format_response
from lab_v4_dev.conversation.semantic_contract import (
    CONTEXTUAL_TRANSITIONS,
    ContextTransition,
    build_semantic_request,
)
from lab_v4_dev.core.contracts import ContextLock, RouteDecision, SessionRef
from lab_v4_dev.llm.prompt_builder import build_chat_prompt
from lab_v4_dev.llm.gateway import ask as gateway_ask
from lab_v4_dev.awareness.agent_self_knowledge import build_agent_self_knowledge
from lab_v4_dev.awareness.knowledge_retriever import retrieve_for_question
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.nlu.context_resolver import is_incomplete
from lab_v4_dev.nlu.conversation_semantics import is_social_act, is_style_act


_AGENT_SELF_INTENTS = {
    Intent.AGENT_IDENTITY,
    Intent.AGENT_CAPABILITIES,
    Intent.AGENT_ARCHITECTURE,
    Intent.AGENT_EXECUTION_FLOW,
    Intent.AGENT_LIMITS,
}

_NON_EXECUTABLE_INTENTS = {
    Intent.UNCLEAR,
    Intent.PERSONAL_CHAT,
    Intent.UNSUPPORTED,
    Intent.HELP,
    *_AGENT_SELF_INTENTS,
    "unclear",
    "unsupported",
    "help",
}


class ConversationManager:
    def __init__(self, orchestrator, dialogue_memory=None, dni=None):
        self.orchestrator = orchestrator
        self.dialogue_memory = dialogue_memory
        self.dni = dni

    @staticmethod
    def _context_lock_for(*, active: bool, session_id: str | None = None, topic: str | None = None, output_kind: str | None = None, reason: str | None = None):
        if active and not any((session_id, topic, output_kind)):
            raise ValueError("an active context lock requires an owner or output")
        return ContextLock(active=bool(active), session_id=session_id, topic=topic, output_kind=output_kind, reason=reason)

    def _effective_session_ref(self):
        if not self.dialogue_memory:
            return None
        accessor = getattr(self.dialogue_memory, "active_restored_session", None)
        if callable(accessor):
            restored = accessor()
            if isinstance(restored, dict) and restored.get("session_id"):
                return SessionRef(session_id=str(restored["session_id"]))
        state = getattr(self.dialogue_memory, "state", None)
        if state is not None:
            active_session = getattr(state, "active_restored_session_id", None)
            if active_session:
                return SessionRef(session_id=str(active_session))
        return None

    def finalize_route(self, user_input: str, parsed: dict | None, mode: str, *, session_ref: SessionRef | None = None, context_lock: ContextLock | None = None):
        parsed = parsed or {}
        intent = getattr(parsed.get("intent"), "value", parsed.get("intent"))
        target = parsed.get("target")
        conversation_act = str(parsed.get("conversation_act") or "NONE").upper()
        raw_text = str(user_input or "")
        normalized = raw_text.casefold()
        summary_marker = any(marker in normalized for marker in ("ملخص", "summary", "summarize", "لخص", "أوجز", "report", "موجز"))

        route = "L-SOCIAL"
        session_scope = "live_current"
        output_kind = "brief"
        evidence_scope = "live_exchanges"
        provider_allowed = False
        topic_filter = None

        if intent in _AGENT_SELF_INTENTS:
            route = "L-FACT"
            output_kind = "capability"
            evidence_scope = "project_state"
            topic_filter = str(target or "agent self knowledge").strip() or None
        elif intent in _NON_EXECUTABLE_INTENTS:
            route = "L-SOCIAL"
            output_kind = "brief"
            evidence_scope = "live_exchanges"
        elif mode == "SYSTEM":
            route = "L-EXEC"
            output_kind = "brief"
            evidence_scope = "work_state"
        elif summary_marker or conversation_act in {"SUMMARIZE", "REPORT", "TOPIC_RETURN", "TOPIC_SHIFT", "CONVERSATION_CONTINUATION"}:
            route = "L-LIVE"
            output_kind = "summary"
            evidence_scope = "live_exchanges"
        elif target is not None:
            route = "L-LIVE"
            output_kind = "continue_topic" if conversation_act in {"TOPIC_RETURN", "CONVERSATION_CONTINUATION"} else "brief"
            evidence_scope = "live_exchanges"
        else:
            route = "CLARIFY"
            output_kind = "none"
            evidence_scope = "none"

        if session_ref is not None:
            session_scope = "saved_number" if session_ref.number is not None else "saved_id"
            evidence_scope = "saved_session"
            if route in {"L-SOCIAL", "L-LIVE", "CLARIFY"}:
                route = "L-SESSION"
            output_kind = "summary" if route == "L-SESSION" and output_kind in {"brief", "none"} else output_kind

        if route == "L-SESSION" and session_ref is None:
            route = "CLARIFY"
            evidence_scope = "none"
            output_kind = "none"

        if route == "DENY":
            provider_allowed = False
        elif route == "P-TOOL":
            provider_allowed = True
        else:
            provider_allowed = False

        lock = context_lock if context_lock is not None else self._context_lock_for(
            active=False,
            session_id=(getattr(session_ref, "session_id", None) if session_ref is not None else None),
            topic=str(target) if target is not None else None,
            output_kind=output_kind or None,
            reason="finalized_route",
        )

        if context_lock is None and session_ref is not None and lock.session_id is not None:
            lock = self._context_lock_for(
                active=True,
                session_id=lock.session_id,
                topic=lock.topic,
                output_kind=output_kind or None,
                reason="saved_session",
            )

        return RouteDecision(
            route=route,
            session_scope=session_scope,
            session_ref=session_ref,
            output_kind=output_kind,
            topic_filter=topic_filter,
            context_lock=lock,
            evidence_scope=evidence_scope,
            provider_allowed=provider_allowed,
            intent=intent,
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            metadata={"mode": mode, "raw_text": raw_text, "target": target, "conversation_act": conversation_act, "source": "conversation_manager.finalize_route"},
        )

    def process(self, user_input: str) -> dict:
        mode = detect_mode(user_input)
        candidate = self._safe_parse(user_input)
        transition = self._classify_context_transition(mode, candidate)
        resolved_input = user_input
        parsed = candidate
        context_entity = None
        if self.dialogue_memory:
            if transition == ContextTransition.RESTORE:
                get_context = getattr(self.dialogue_memory, "context_for_topic", None)
                if callable(get_context):
                    context_entity = get_context(candidate.get("target"))
            elif transition.value in CONTEXTUAL_TRANSITIONS:
                get_active_context = getattr(self.dialogue_memory, "active_context_entity", None)
                if callable(get_active_context):
                    context_entity = get_active_context()

        if self.dialogue_memory and context_entity and transition.value in CONTEXTUAL_TRANSITIONS:
            resolved_input = self.dialogue_memory.resolve_references(user_input, context_entity=context_entity)
            if resolved_input != user_input:
                parsed = self._safe_parse(resolved_input, context_entity=context_entity)

        chat_history = self._history_for_transition(transition, parsed)

        parsed = dict(parsed or {})
        conversation_act = str(parsed.get("conversation_act") or "NONE")
        if transition == ContextTransition.RESTORE:
            conversation_act = "TOPIC_RETURN"
        elif transition == ContextTransition.EXPLICIT_SWITCH:
            conversation_act = "TOPIC_SHIFT"
        elif transition.value in CONTEXTUAL_TRANSITIONS and conversation_act == "NONE":
            conversation_act = "CONVERSATION_CONTINUATION"
        parsed["conversation_act"] = conversation_act
        parsed.setdefault("conversation_domain", "general")
        parsed.setdefault("conversation_confidence", 0.0)
        parsed.setdefault("response_attributes", {})

        semantic = build_semantic_request(
            user_input,
            mode,
            intent=getattr(parsed.get("intent"), "value", parsed.get("intent")),
            conversation_domain=parsed.get("conversation_domain", "general"),
            conversation_act=conversation_act,
            conversation_confidence=float(parsed.get("conversation_confidence", 0.0) or 0.0),
            response_attributes=parsed.get("response_attributes") or {},
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            target=(parsed.get("target") or (context_entity.get("entity") if context_entity and transition.value in CONTEXTUAL_TRANSITIONS else None)),
            requires_context=(transition.value in CONTEXTUAL_TRANSITIONS),
            context_transition=transition,
        )

        session_ref = self._effective_session_ref()
        route_decision = self.finalize_route(user_input, parsed, mode, session_ref=session_ref, context_lock=self._context_lock_for(
            active=bool(context_entity and transition.value in CONTEXTUAL_TRANSITIONS),
            session_id=(getattr(session_ref, "session_id", None) if session_ref is not None else None),
            topic=(context_entity.get("entity") if isinstance(context_entity, dict) else None),
            output_kind=("continue_topic" if transition.value in CONTEXTUAL_TRANSITIONS else "brief"),
            reason="process_context",
        ) if context_entity is not None else None)

        result = self._dispatch(resolved_input, mode, parsed, user_question=user_input, chat_history=chat_history, route_decision=route_decision)

        result = dict(result)
        result["semantic_request"] = semantic.as_dict()
        result["_route_decision"] = route_decision
        if result.get("text"):
            result["text"] = format_response(result["text"], mode)
        if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
            self.dialogue_memory.update(user_input, result, mode=mode, parsed=parsed, context_transition=transition)
        return result

    def _dispatch(self, text, mode, parsed, *, user_question=None, chat_history=None, route_decision=None):
        if route_decision is not None:
            return self._dispatch_by_route(text, mode, parsed, route_decision, user_question=user_question, chat_history=chat_history)
        intent = parsed.get("intent") if parsed else None
        if intent in _AGENT_SELF_INTENTS:
            return self._handle_chat(text, mode, parsed=parsed, user_question=user_question or text, history=chat_history)
        if mode == "SYSTEM":
            result = self.orchestrator.handle(text, parsed=parsed, context_resolved=True)
            return {**dict(result), "executed": result.get("status") != "needs_clarification"}
        if intent not in _NON_EXECUTABLE_INTENTS:
            result = self.orchestrator.handle(text, parsed=parsed, context_resolved=True)
            return {**dict(result), "executed": result.get("status") != "needs_clarification"}
        return self._handle_chat(text, mode, parsed=parsed, user_question=user_question or text, history=chat_history)

    def _dispatch_by_route(self, text, mode, parsed, route_decision, *, user_question=None, chat_history=None):
        route = route_decision.route
        if route not in {"L-SOCIAL", "L-LIVE", "L-SESSION", "L-FACT", "L-EXEC", "P-TOOL", "CLARIFY", "DENY"}:
            raise ValueError(f"invalid route: {route}")

        if route == "L-EXEC":
            result = self.orchestrator.handle(text, parsed=parsed, context_resolved=True)
            return {**dict(result), "executed": result.get("status") != "needs_clarification", "evidence_scope": route_decision.evidence_scope}
        if route == "CLARIFY":
            return {"status": "needs_clarification", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "أحتاج إلى توضيح نقطة الهدف قبل المتابعة.", "mode": mode, "source": "clarify", "executed": False, "evidence_scope": route_decision.evidence_scope, "_route_decision": route_decision}
        if route == "DENY":
            return {"status": "denied", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "تم رفض هذا الطلب لأن المسار غير مسموح به من حيث السياسة الحالية.", "mode": mode, "source": "deny", "executed": False, "evidence_scope": route_decision.evidence_scope, "_route_decision": route_decision}
        if route == "L-SOCIAL":
            return self._handle_local_response(text, mode, parsed, route_decision, user_question=user_question, history=chat_history, output_kind=route_decision.output_kind)
        if route == "L-LIVE":
            return self._handle_local_response(text, mode, parsed, route_decision, user_question=user_question, history=chat_history, output_kind=route_decision.output_kind)
        if route == "L-SESSION":
            return self._handle_local_response(text, mode, parsed, route_decision, user_question=user_question, history=chat_history, output_kind=route_decision.output_kind)
        if route == "L-FACT":
            return self._handle_local_response(text, mode, parsed, route_decision, user_question=user_question, history=chat_history, output_kind=route_decision.output_kind)
        if route == "P-TOOL":
            if not route_decision.provider_allowed:
                return {"status": "denied", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "المزود غير مسموح به في القرار الحالي.", "mode": mode, "source": "provider_blocked", "executed": False, "provider_allowed": False, "evidence_scope": route_decision.evidence_scope}
            return self._handle_chat(text, mode, parsed=parsed, user_question=user_question or text, history=chat_history, route_decision=route_decision)
        return self._handle_local_response(text, mode, parsed, route_decision, user_question=user_question, history=chat_history, output_kind=route_decision.output_kind)

    def _handle_local_response(self, text, mode, parsed, route_decision, *, user_question=None, history=None, output_kind=None):
        if route_decision is not None and not route_decision.provider_allowed:
            return self._local_policy_fallback(route_decision, text, mode, parsed, output_kind or route_decision.output_kind)
        if route_decision is not None and route_decision.provider_allowed:
            return self._handle_chat(text, mode, parsed=parsed, user_question=user_question or text, history=history, route_decision=route_decision)
        return self._handle_chat(text, mode, parsed=parsed, user_question=user_question or text, history=history, route_decision=route_decision)

    def _local_policy_fallback(self, route_decision, text, mode, parsed, output_kind):
        evidence_scope = getattr(route_decision, "evidence_scope", "none")
        if output_kind == "summary":
            return {"status": "local", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "ملخص محلي: لا يعالج هذا الطلب مزودًا خارجيًا في السياق الحالي.", "mode": mode, "source": "local_summary", "executed": False, "provider_allowed": False, "evidence_scope": evidence_scope}
        if output_kind == "capability":
            return {"status": "local", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "القدرات متاحة محليًا، ولا يُسمح باستدعاء المزود في هذا القرار.", "mode": mode, "source": "local_capability", "executed": False, "provider_allowed": False, "evidence_scope": evidence_scope}
        return {"status": "local", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "تمت معالجة الطلب محليًا دون استدعاء المزود الخارجي لأن الإذن غير مسموح به في القرار الحالي.", "mode": mode, "source": "local_fallback", "executed": False, "provider_allowed": False, "evidence_scope": evidence_scope}

    def _handle_chat(self, text, mode, *, parsed=None, user_question=None, history=None, route_decision=None):
        if route_decision is not None and not route_decision.provider_allowed:
            return self._local_policy_fallback(route_decision, text, mode, parsed or {}, route_decision.output_kind)
        result = {}
        try:
            intent = (parsed or {}).get("intent")
            self_knowledge = build_agent_self_knowledge(intent) if intent in _AGENT_SELF_INTENTS else None
            project_knowledge = None
            if user_question and intent in _AGENT_SELF_INTENTS:
                try:
                    project_knowledge = retrieve_for_question(user_question)
                except Exception:
                    project_knowledge = None
            system, prompt = build_chat_prompt(text, list(history or []), agent_self_knowledge=self_knowledge, project_knowledge=project_knowledge, conversation_semantics={"conversation_domain": (parsed or {}).get("conversation_domain", "general"), "conversation_act": (parsed or {}).get("conversation_act", "NONE"), "response_attributes": (parsed or {}).get("response_attributes", {})})
            result = gateway_ask(prompt, system=system, max_tokens=4000 if self_knowledge else 1600, temperature=0.7, routing_text=text)
            if result.get("status") != "success":
                raise RuntimeError(result.get("message"))
            reply = result.get("text", "")
            if not reply:
                raise ValueError("empty")
            return {"status": "success", "intent": (parsed or {}).get("intent", mode.lower()), "text": reply, "mode": mode, "source": "llm", "provider_used": result.get("provider_used"), "provider_chain": result.get("provider_chain", []), "model": result.get("model"), "executed": False}
        except Exception:
            fallback = "تعذر الوصول إلى نموذج الذكاء الاصطناعي حالياً. تحقق من الاتصال أو إعدادات المزود ثم أعد المحاولة."
            return {"status": "error", "intent": (parsed or {}).get("intent", mode.lower()), "text": fallback, "mode": mode, "source": "fallback", "provider_used": result.get("provider_used") if isinstance(result, dict) else None, "provider_chain": result.get("provider_chain", []) if isinstance(result, dict) else [], "model": result.get("model") if isinstance(result, dict) else None, "gateway_error": result.get("error") if isinstance(result, dict) else None, "executed": False}

    def _safe_parse(self, text: str, *, context_entity: dict | None = None) -> dict:
        try:
            if context_entity:
                result = parse(text, context_entity=context_entity)
            else:
                result = parse(text)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def _classify_context_transition(self, mode: str, parsed: dict) -> ContextTransition:
        parsed = parsed or {}
        entity_type = str(parsed.get("entity_type", "")).upper()
        target = str(parsed.get("target") or "").strip()
        intent = getattr(parsed.get("intent"), "value", parsed.get("intent"))
        pattern = parsed.get("semantic_pattern")
        active_context = None
        if self.dialogue_memory:
            get_active_context = getattr(self.dialogue_memory, "active_context_entity", None)
            if callable(get_active_context):
                active_context = get_active_context()
        active_topic = active_context.get("entity") if isinstance(active_context, dict) else None

        conversation_act = parsed.get("conversation_act")
        if intent in _AGENT_SELF_INTENTS:
            return ContextTransition.NEW_INDEPENDENT
        if is_style_act(conversation_act) and not target:
            return ContextTransition.CONTINUE if active_topic else ContextTransition.AMBIGUOUS
        if is_social_act(conversation_act) and str(conversation_act).upper() != "CASUAL_CONVERSATION" and not target:
            return ContextTransition.AMBIGUOUS
        if entity_type == "REFERENCE":
            return ContextTransition.REFERENCE if active_topic else ContextTransition.AMBIGUOUS
        if target:
            if active_topic and self._same_topic(target, active_topic):
                return ContextTransition.CONTINUE
            previous_context = None
            if self.dialogue_memory:
                get_context = getattr(self.dialogue_memory, "context_for_topic", None)
                if callable(get_context):
                    previous_context = get_context(target)
                pending_topic = getattr(self.dialogue_memory, "pending_topic", None)
            else:
                pending_topic = None
            valid_target = entity_type not in {"", "UNKNOWN", "REFERENCE", "ELABORATION"}
            if valid_target and (previous_context or self._same_topic(target, pending_topic)):
                return ContextTransition.RESTORE
            return ContextTransition.EXPLICIT_SWITCH if active_topic else ContextTransition.NEW_INDEPENDENT
        if entity_type == "ELABORATION":
            return ContextTransition.CONTINUE if active_topic else ContextTransition.AMBIGUOUS
        if pattern in {"CONTINUE_WORK", "GIVE_EXAMPLE"}:
            return ContextTransition.CONTINUE if active_topic else ContextTransition.AMBIGUOUS
        if mode == "FOLLOW_UP":
            if not active_topic:
                return ContextTransition.AMBIGUOUS
            previous_intent = getattr(getattr(self.dialogue_memory, "state", None), "last_intent", None) if self.dialogue_memory else None
            previous_intent = getattr(previous_intent, "value", previous_intent)
            return ContextTransition.CONTINUE if intent and intent == previous_intent else ContextTransition.REFERENCE
        if mode == "CHAT" and intent in _NON_EXECUTABLE_INTENTS:
            return ContextTransition.AMBIGUOUS
        incomplete = is_incomplete({"intent": intent or "", "target": "", "entity": {"value": ""}})
        if incomplete or not intent:
            return ContextTransition.AMBIGUOUS
        return ContextTransition.NEW_INDEPENDENT

    @staticmethod
    def _same_topic(left, right) -> bool:
        def normalize_topic(value):
            return " ".join(str(value).casefold().strip(" \t\r\n.,،؛:!?؟()[]{}\"'").split())
        return normalize_topic(left) == normalize_topic(right)

    def _history_for_transition(self, transition, parsed):
        if not self.dialogue_memory:
            return []
        if transition == ContextTransition.RESTORE:
            topic = (parsed or {}).get("target")
        elif transition.value in CONTEXTUAL_TRANSITIONS:
            active_context = self.dialogue_memory.active_context_entity()
            topic = active_context.get("entity") if isinstance(active_context, dict) else None
        elif transition == ContextTransition.EXPLICIT_SWITCH:
            topic = (parsed or {}).get("target")
        elif transition == ContextTransition.AMBIGUOUS and is_social_act((parsed or {}).get("conversation_act")):
            state = getattr(self.dialogue_memory, "state", None)
            history = getattr(state, "history", []) if state is not None else []
            return [turn for turn in history if isinstance(turn, dict) and not turn.get("target")][-8:]
        else:
            return []
        if not topic:
            return []
        state = getattr(self.dialogue_memory, "state", None)
        history = getattr(state, "history", []) if state is not None else []
        return [turn for turn in history if isinstance(turn, dict) and turn.get("target") and self._same_topic(turn.get("target"), topic)]

    def _handle_task(self, text: str) -> dict:
        return self.process(text)

    def _handle_system(self, text: str) -> dict:
        return self.process(text)

    def _handle_follow_up(self, text: str) -> dict:
        return self.process(text)

    def _handle_output(self, route_decision, text, mode, parsed, *, history=None):
        output_kind = getattr(route_decision, "output_kind", "none")
        if output_kind == "summary":
            return {"status": "success", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "ملخص محلي للطلب الحالي وفق مصدر الأدلة المختار.", "mode": mode, "source": "summary_output", "executed": False, "evidence_scope": route_decision.evidence_scope}
        if output_kind == "capability":
            return {"status": "success", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "القدرات متاحة محليًا وفق القرار الحالي.", "mode": mode, "source": "capability_output", "executed": False, "evidence_scope": route_decision.evidence_scope}
        if output_kind == "transcript":
            return {"status": "success", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": text or "لا يوجد نص متاح للنسخ.", "mode": mode, "source": "transcript_output", "executed": False, "evidence_scope": route_decision.evidence_scope}
        if output_kind == "continue_topic":
            return {"status": "success", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "استئناف الموضوع الحالي باستخدام السياق المسموح به فقط.", "mode": mode, "source": "continue_topic_output", "executed": False, "evidence_scope": route_decision.evidence_scope}
        if output_kind == "brief":
            return {"status": "success", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": "إجابة موجزة محلية وفق السياسة الحالية.", "mode": mode, "source": "brief_output", "executed": False, "evidence_scope": route_decision.evidence_scope}
        return {"status": "success", "intent": getattr(parsed.get("intent"), "value", parsed.get("intent")), "text": text or "رد محلي بدون مخرجات متخصصة.", "mode": mode, "source": "local_output", "executed": False, "evidence_scope": route_decision.evidence_scope}

    def switch_topic(self, current_topic: str, new_input: str) -> dict:
        if self.dialogue_memory:
            self.dialogue_memory.save_pending(current_topic)
        return self.process(new_input)

    def restore_topic(self) -> dict:
        if self.dialogue_memory:
            topic = getattr(self.dialogue_memory, "pending_topic", None)
            if topic:
                result = dict(self.process(f"ارجع لشرح {topic}"))
                result.setdefault("topic", topic)
                return result
        return {"status": "success", "intent": "topic_restore", "text": "لا يوجد موضوع مؤجل."}


__all__ = ["ConversationManager"]


if __name__ == "__main__":
    print("conversation_manager")












































































































































































































































































































































































































































































































































































































































































































































n




























































































n
"}]}],