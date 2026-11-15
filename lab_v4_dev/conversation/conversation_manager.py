"""
Conversation Manager — Unified Conversation/Intent Routing.

Authority contract:

ModeDetector
    -> conversational shape only.

IntentParser
    -> canonical semantic resolver for the current text, without implicit
       persistent context.

Context
    -> enriches references/targets only.

ConversationManager
    -> authorizes context transitions before final resolution and chooses
       ONE execution owner.

Orchestrator
    -> sole execution owner for operational requests.

LLM
    -> conversational and evidence-backed knowledge responder for
       non-operational turns, including context-authorized project continuations.

Important:
FOLLOW_UP is a conversational MODE, not an automatic LLM route.
Explicit executable intents go to Orchestrator. A contextual project
continuation that was promoted to CYBER_EXPLAIN only because the active
branch is a PROJECT remains a knowledge-backed conversational response,
unless the current turn explicitly requests an operation.
"""

import re
import inspect

from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.conversation.assistant_style import format_response, single_question
from lab_v4_dev.conversation.local_response_engine import answer_local_social
from lab_v4_dev.conversation.unified_local_response import answer_local_response
from lab_v4_dev.conversation.semantic_contract import (
    CONTEXTUAL_TRANSITIONS,
    ContextTransition,
    build_semantic_request,
)
from lab_v4_dev.llm.prompt_builder import build_chat_prompt
from lab_v4_dev.llm.gateway import ask as gateway_ask
from lab_v4_dev.awareness.agent_self_knowledge import build_agent_self_knowledge
from lab_v4_dev.awareness.knowledge_retriever import (
    ProjectScope,
    QuestionClassifier,
    resolve_project_scope,
    retrieve_for_question,
)
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.core.contracts import RouteDecision, SessionRef, ContextLock
from lab_v4_dev.nlu.context_resolver import is_incomplete
from lab_v4_dev.nlu.conversation_semantics import (
    is_social_act,
    is_style_act,
    normalize_text,
)


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
        # A read-only saved-session report owns short follow-up turns until
        # the user starts a different request or selects another session.
        self.active_report_session_id = None
        self.active_report_topic_filter = None
        self.active_live_output_kind = None
        self.context_lock = ContextLock()

    def finalize_route(
        self,
        *,
        parsed: dict,
        selected_session: dict,
        saved_session_request: bool,
        selected_saved_session_id: str | None,
        transition: ContextTransition,
        route_override: str | None = None,
        provider_allowed_ceiling: bool | None = None,
    ) -> RouteDecision:
        """Issue the immutable final route after semantic/context resolution.

        The selector and parser are inputs only. This method resolves the
        response owner, saved/live evidence boundary, output contract and
        provider permission once; downstream code must consume this value.
        """
        parsed = parsed if isinstance(parsed, dict) else {}
        selected_session = selected_session if isinstance(selected_session, dict) else {}
        intent = parsed.get("intent")
        intent_value = str(getattr(intent, "value", intent) or "").casefold()
        domain = str(parsed.get("conversation_domain") or "general").casefold()
        act = str(parsed.get("conversation_act") or "NONE").upper()
        response_attributes = parsed.get("response_attributes") or {}
        history_request = bool(
            act in {"CONVERSATION_HISTORY_QUERY", "CONVERSATION_HISTORY_SUMMARY"}
            or response_attributes.get("dialogue_recall")
            or response_attributes.get("history_query")
        ) and domain not in {"technical", "execution", "project"} and not response_attributes.get("dialogue_feature_discussion")
        selector_kind = str(selected_session.get("kind") or "none").casefold()
        session_id = str(selected_saved_session_id or selected_session.get("session_id") or "").strip()
        session_number = selected_session.get("number")

        if not session_id and selector_kind == "number" and session_number is not None:
            try:
                from lab_v4_dev.memory.session_state import get_session_by_number
                selected_record = get_session_by_number(int(session_number))
                session_id = str(selected_record.get("session_id") or "").strip()
            except (TypeError, ValueError):
                session_id = ""
        if not session_id and selector_kind == "latest":
            try:
                from lab_v4_dev.memory.session_state import get_session_index, _session_updated_key
                records = sorted(get_session_index(), key=_session_updated_key, reverse=True)
                selected_record = records[0] if records else {}
                session_id = str(selected_record.get("session_id") or "").strip()
            except Exception:
                session_id = ""
        if not session_id and selector_kind == "search":
            query = str(selected_session.get("query") or selected_session.get("topic_filter") or "").strip()
            if query:
                try:
                    from lab_v4_dev.memory.session_state import search_sessions
                    matches = search_sessions(query, limit=2)
                    if len(matches) == 1:
                        session_id = str(matches[0].get("session_id") or "").strip()
                except Exception:
                    session_id = ""
        if not session_id and selector_kind == "previous_dialogue":
            try:
                from lab_v4_dev.memory.session_state import get_previous_saved_dialogue
                selector_state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
                current_dialogue_id = str(getattr(selector_state, "session_id", "") or "").strip()
                selected_record = get_previous_saved_dialogue(
                    exclude_session_id=current_dialogue_id,
                )
                session_id = str(selected_record.get("session_id") or "").strip()
            except Exception:
                session_id = ""

        if saved_session_request or selector_kind not in {"none", "reference", "count", "list", "compare", "status"}:
            route = "L-SESSION"
        elif history_request:
            route = "L-LIVE"
        elif act in {"SOCIAL_GREETING", "SOCIAL_CLOSING"}:
            # A greeting addressed to the agent remains a social turn.
            route = "L-SOCIAL"
        elif response_attributes.get("dialogue_context_reference"):
            # Meta-questions about what the user meant or why the dialogue drifted
            # must use the active dialogue context, not static agent-self facts.
            route = "L-LIVE"
        elif intent_value in {
            str(getattr(item, "value", item)).casefold()
            for item in _AGENT_SELF_INTENTS
        }:
            # Agent self-queries need local evidence; the provider remains a response composer.
            route = "L-FACT"
        elif intent_value == "cyber_explain":
            if domain == "project":
                route = "L-FACT"
            else:
                # CYBER_EXPLAIN is already the parser's explicit technical
                # explanation intent. Do not demote it to generic live chat
                # merely because the domain classifier underlabels the subject.
                # Missing/ambiguous subjects are clarified by the tool owner.
                route = "P-TOOL"
        elif intent_value == "architecture":
            route = "L-FACT" if domain == "project" else "P-TOOL"
        elif intent_value == "propose_solution" and not str(parsed.get("target") or "").strip():
            # Recognized invitation phrases use the local social composer;
            # broader generic proposal requests use the dialogue gateway.
            route = (
                "L-SOCIAL" if response_attributes.get("local_social_suggestion")
                else "L-LIVE"
            ) if domain != "execution" else "L-EXEC"
        elif intent_value in {"plan", "lab_plan"} and not str(parsed.get("target") or "").strip():
            route = "L-LIVE" if domain != "execution" else "L-EXEC"
        elif intent_value in {"propose_solution", "plan", "lab_plan"} and str(parsed.get("target") or "").strip():
            route = "P-TOOL"
        elif response_attributes.get("compound_request"):
            route = "L-LIVE"
        elif act in {"CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY", "TOPIC_RETURN"}:
            route = "P-TOOL" if domain == "technical" else "L-LIVE"
        elif intent_value in {str(getattr(item, "value", item)).casefold() for item in _NON_EXECUTABLE_INTENTS}:
            if domain == "project":
                route = "L-FACT"
            elif domain == "technical":
                route = "P-TOOL"
            elif act == "SOCIAL_OPENING" and str(parsed.get("target") or "").strip():
                route = "L-LIVE"
            elif act in {"CASUAL_CONVERSATION", "CASUAL_DISCUSSION", "PERSONAL_INTERACTION", "SOCIAL_FOLLOW_UP"}:
                route = "L-LIVE"
            elif act in {
                "SOCIAL_GREETING", "SOCIAL_CLOSING", "SOCIAL_ACKNOWLEDGEMENT", "SOCIAL_OPENING",
            }:
                # Domain classification alone must not force a substantive
                # topic shift into the local-only social route. TOPIC_SHIFT
                # and other open-ended turns require the live dialogue gateway.
                route = "L-SOCIAL"
            else:
                route = "L-LIVE"
        else:
            route = "L-EXEC"
        if route_override is not None:
            if route_override not in {"L-SOCIAL", "L-LIVE", "L-SESSION", "L-FACT", "L-EXEC", "P-TOOL", "CLARIFY", "DENY"}:
                raise ValueError(f"invalid route override: {route_override}")
            route = route_override

        live_state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        live_session_id = str(getattr(live_state, "session_id", "") or "")
        live_archive = getattr(live_state, "exchange_archive", []) if live_state is not None else []
        live_history = getattr(live_state, "history", []) if live_state is not None else []

        def is_live_dialogue_record(item):
            if not isinstance(item, dict):
                return False
            item_session = str(item.get("session_id") or "")
            if live_session_id and item_session and item_session != live_session_id:
                return False
            kind = str(item.get("context_kind") or "dialogue").casefold()
            domain = str(item.get("conversation_domain") or "general").casefold()
            return (
                kind not in {"work", "system", "execution"}
                and domain not in {"work", "system", "execution"}
                and not item.get("recall_only")
                and not item.get("state_boundary_only")
            )

        archive_evidence = any(
            is_live_dialogue_record(item)
            and str(item.get("user") or "").strip()
            and str(item.get("assistant") or "").strip()
            for item in (live_archive or [])
        )
        history_has_user = any(
            is_live_dialogue_record(item)
            and item.get("role") == "user"
            and str(item.get("content") or "").strip()
            for item in (live_history or [])
        )
        history_has_assistant = any(
            is_live_dialogue_record(item)
            and item.get("role") == "assistant"
            and str(item.get("content") or "").strip()
            for item in (live_history or [])
        )
        has_live_exchange_evidence = bool(
            archive_evidence or (history_has_user and history_has_assistant)
        )
        has_live_dialogue = bool(
            has_live_exchange_evidence
            or (live_state is not None and (
                getattr(live_state, "context_history", [])
                or getattr(live_state, "last_topic", None)
            ))
            or bool(
                callable(getattr(self.dialogue_memory, "active_context_entity", None))
                and self.dialogue_memory.active_context_entity()
            )
        )
        requested_output_hint = str(
            selected_session.get("output_kind") or parsed.get("output_kind") or "none"
        )
        explicit_history_request = history_request
        live_history_output = (
            requested_output_hint in {
                "brief", "summary", "report", "topic_summary", "transcript",
            } or explicit_history_request
        ) and selector_kind in {"none", "reference"}
        if live_history_output and not has_live_exchange_evidence:
            route = "CLARIFY"
        if selector_kind == "reference" and not has_live_dialogue and selected_session.get("output_kind") in {
            "brief", "summary", "report", "topic_summary", "transcript",
        }:
            route = "CLARIFY"

        if route == "L-SESSION" and session_id:
            if selector_kind == "number" and session_number is not None:
                session_scope = "saved_number"
                session_ref = SessionRef(session_id=session_id, number=int(session_number))
            elif selector_kind in {"latest", "previous_dialogue"}:
                session_scope = "previous_saved"
                session_ref = SessionRef(session_id=session_id)
            else:
                session_scope = "saved_id"
                session_ref = SessionRef(session_id=session_id)
        elif route == "L-SESSION":
            session_scope = "none"
            session_ref = None
        elif route != "CLARIFY" and (
            (
                selector_kind in {"none", "reference"}
                and has_live_exchange_evidence
                and live_history_output
            ) or (
                selector_kind == "reference" and has_live_dialogue
            ) or (transition in CONTEXTUAL_TRANSITIONS and has_live_dialogue)
        ):
            session_scope = "live_current"
            session_ref = None
        else:
            session_scope = "none"
            session_ref = None

        requested_output = str(selected_session.get("output_kind") or parsed.get("output_kind") or "none")
        if requested_output == "chat" or requested_output not in {"none", "brief", "summary", "report", "topic_summary", "transcript", "list", "continue_topic", "capability", "session_number", "session_identity"}:
            requested_output = "none"
        if route == "CLARIFY":
            requested_output = "none"
        elif route == "L-SESSION" and session_ref is None and selector_kind not in {"collection", "list"}:
            # Search/ambiguous selectors are not evidence yet. Keep the
            # report mode in selector metadata until an exact session resolves.
            requested_output = "none"
        elif route == "L-SESSION" and requested_output == "none" and selector_kind not in {"collection", "list"}:
            requested_output = "report"
        if route == "L-SESSION" and session_ref is not None:
            evidence_scope = "saved_session"
        elif (
            route == "L-SESSION"
            and selector_kind in {"collection", "list"}
            and requested_output == "report"
        ):
            # A collection report reads the saved-session index and detail
            # records as a collection, not one selected saved session.
            evidence_scope = "saved_sessions"
        elif route == "L-FACT":
            evidence_scope = "project_state"
        elif route == "L-EXEC":
            evidence_scope = "work_state"
        elif session_scope == "live_current":
            evidence_scope = "live_exchanges"
        else:
            evidence_scope = "none"

        live_session_id = str(getattr(live_state, "session_id", "") or "").strip()
        live_topic = str(
            parsed.get("target")
            or getattr(live_state, "last_topic", None)
            or ""
        ).strip()
        locked_topic_value = (
            selected_session.get("topic_filter") if route == "L-SESSION" else live_topic
        )
        locked_topic = str(locked_topic_value or "").strip() or None
        # A collection/list or unresolved search is not a single session owner.
        # Only an exact SessionRef may establish a saved-session context lock.
        lock_active = bool(
            (route == "L-SESSION" and session_ref is not None)
            or (session_scope == "live_current" and (live_session_id or locked_topic))
        )
        lock = ContextLock(
            active=lock_active,
            session_id=(
                session_ref.session_id if session_ref
                else live_session_id if session_scope == "live_current" and live_session_id
                else None
            ),
            topic=locked_topic,
            output_kind=requested_output if requested_output != "none" else None,
            reason=(
                "saved_session_selection" if route == "L-SESSION" and lock_active
                else "live_dialogue_context" if lock_active
                else None
            ),
        )
        provider_allowed = (
            route in {"L-FACT", "L-LIVE", "P-TOOL", "L-EXEC"}
            or (
                route == "L-SESSION"
                and requested_output in {"summary", "report", "topic_summary"}
                and bool(getattr(
                    getattr(self.orchestrator, "agent", None),
                    "allow_provider_session_synthesis",
                    False,
                ))
            )
        )
        if provider_allowed_ceiling is not None:
            provider_allowed = provider_allowed and bool(provider_allowed_ceiling)

        return RouteDecision(
            route=route,
            session_scope=session_scope,
            session_ref=session_ref,
            output_kind=requested_output,
            topic_filter=str(selected_session.get("topic_filter") or "").strip() or None,
            context_lock=lock,
            evidence_scope=evidence_scope,
            provider_allowed=provider_allowed,
            intent=intent,
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            metadata={
                "selector_kind": selector_kind,
                "saved_session_request": bool(saved_session_request),
                "context_transition": transition.value,
                **({"clarification_reason": "missing_live_evidence"}
                   if route == "CLARIFY" and live_history_output and not has_live_exchange_evidence else {}),
                **({
                    "evidence_collection": (
                        "saved_sessions" if requested_output == "report" else "saved_dialogues"
                    )
                } if selector_kind in {"collection", "list"} else {}),
            },
        )

    @staticmethod
    def _is_project_progress_request(text: str) -> bool:
        """Recognize project-state questions by combining intent cues, not a single keyword."""
        normalized = normalize_text(str(text or ""))
        status_cues = (
            "اين توقف", "اين وصل", "اين انتهي العمل", "حاله العمل",
            "حاله المشروع", "سياق العمل", "عن سياق العمل", "نفس سياق العمل",
            "في نفس سؤال", "نفس سؤال", "اكمل الشرح", "استكمل الشرح",
            "تابع الشرح", "تقدم العمل", "ما انجز", "ماذا انجز",
            "ما المتبقي", "الخطوه التاليه", "اخر خطوه",
            "where did we stop", "project status", "next step",
        )
        plan_cues = (
            "خطه العمل", "خطه تطوير", "الخطه القادمه", "ما الخطه",
            "ماهي الخطه", "ما هي خطه", "what is the plan", "project roadmap",
        )

        # Questions about what we were developing are project-progress
        # questions, not generic architecture questions. Require both a
        # project artefact (layer/function/module/file/feature) and a
        # collaborative development action so ordinary theory questions do
        # not become current-project lookups.
        development_entities = (
            "طبقه", "طبقات", "وظيفه", "وظائف", "وضائف", "وضيفه",
            "مكون", "مكونات", "وحده", "وحدات", "ميزه", "ميزات",
            "ملف", "ملفات", "مسار", "مسارات",
        )
        development_actions = (
            "كنا نطور", "كنا نعدل", "كنا نصلح", "كنا نعمل",
            "نحن نطور", "نحن نعدل", "نحن نصلح", "التي نطور",
            "التي نعمل", "التي نعدل", "نطورها", "نعدلها",
            "نعمل على", "نشتغل على",
        )
        development_inventory = (
            any(cue in normalized for cue in development_entities)
            and any(cue in normalized for cue in development_actions)
        )
        return (
            any(cue in normalized for cue in status_cues + plan_cues)
            or development_inventory
        )

    def _local_project_progress_answer(
        self,
        text: str,
        parsed: dict,
        context_entity: dict | None,
    ) -> dict | None:
        """Answer explicit project progress/plan questions from the local project-state record."""
        normalized_request = normalize_text(str(text or ""))
        explicitly_general_scope = any(marker in normalized_request for marker in (
            "بصفه عامه", "بشكل عام", "بصوره عامه", "عموما",
            "محادثه وديه", "دردشه وديه", "خارج بنية المشروع",
            "لا نتحدث عن مشروع", "ليس عن مشروع",
            "بلا علاقه بالمشروع", "not about cyberlab",
            "outside cyberlab", "general discussion",
        ))
        if (
            not self._is_project_progress_request(text)
            or explicitly_general_scope
        ):
            return None

        if self.dialogue_memory:
            get_active_context = getattr(
                self.dialogue_memory, "active_context_entity", None
            )
            active_context = get_active_context() if callable(get_active_context) else None
            active_is_project = (
                isinstance(active_context, dict)
                and str(active_context.get("entity_type") or "").upper() == "PROJECT"
            )
            passed_is_project = (
                isinstance(context_entity, dict)
                and (
                    str(context_entity.get("entity_type") or "").upper() == "PROJECT"
                    or str(context_entity.get("conversation_domain") or "").casefold() == "project"
                )
            )
            if active_is_project and not passed_is_project:
                # The project branch itself is the authorization anchor for
                # "what were we developing?" questions. Do not trust a fresh
                # generic/unknown lexical target over the active project owner.
                context_entity = active_context

        context_parts = [str(text or "")]
        if isinstance(parsed, dict):
            context_parts.extend((
                str(parsed.get("target") or ""),
                str(parsed.get("conversation_domain") or ""),
            ))
        if isinstance(context_entity, dict):
            context_parts.extend((
                str(context_entity.get("entity") or ""),
                str(context_entity.get("conversation_domain") or ""),
            ))
        scope_text = " ".join(part for part in context_parts if part)
        intent = (parsed or {}).get("intent")
        scope = resolve_project_scope(scope_text, intent=intent)
        # Preserve explicit external/generic/historical scope even when an
        # older project branch remains active in dialogue memory.
        if scope in {
            ProjectScope.EXTERNAL_PROJECT,
            ProjectScope.GENERIC_PROJECT,
            ProjectScope.HISTORICAL_PROJECT,
        }:
            return None
        parsed_domain = str(
            (parsed or {}).get("conversation_domain") or ""
        ).casefold()
        context_authorizes_project = (
            parsed_domain == "project"
            or (
                isinstance(context_entity, dict)
                and (
                    str(context_entity.get("conversation_domain") or "").casefold() == "project"
                    or str(context_entity.get("entity_type") or "").upper() == "PROJECT"
                )
            )
        )
        if scope != ProjectScope.CURRENT_PROJECT and context_authorizes_project:
            scope = ProjectScope.CURRENT_PROJECT
        if scope != ProjectScope.CURRENT_PROJECT:
            return None

        try:
            from lab_v4_dev.awareness.project_knowledge import get_project_state
            state = get_project_state()
        except Exception as exc:
            state = {}
            retrieval_error = type(exc).__name__
        else:
            retrieval_error = ""

        state = state if isinstance(state, dict) else {}

        def usable(value):
            if value is None:
                return False
            if isinstance(value, str):
                return value.strip().casefold() not in {"", "?", "unknown", "غير معروف", "غير متاح"}
            if isinstance(value, (list, tuple, set, dict)):
                return bool(value)
            return True

        lines = ["وفق سجل حالة المشروع المحلي:"]
        fields = (
            ("current_focus", "التركيز الحالي"),
            ("last_goal", "آخر هدف محفوظ"),
            ("last_step", "الخطوة التالية المسجلة"),
        )
        evidence_count = 0
        for key, label in fields:
            value = state.get(key)
            if usable(value):
                lines.append(f"- {label}: {value}")
                evidence_count += 1

        for key, label in (("active", "الأعمال النشطة"), ("planned", "الأعمال المخططة")):
            values = state.get(key)
            if usable(values):
                rendered = [str(item).strip() for item in values if str(item).strip()]
                if rendered:
                    lines.append(f"- {label}: " + "؛ ".join(rendered[:5]))
                    evidence_count += 1

        completed_count = state.get("completed_count")
        if isinstance(completed_count, int) and completed_count > 0:
            lines.append(f"- العناصر المكتملة المسجلة: {completed_count}")
            evidence_count += 1

        if not evidence_count:
            detail = (
                f" تعذر قراءة السجل بسبب {retrieval_error}."
                if retrieval_error else
                " السجل لا يحتوي على تركيز أو خطوة تالية أو عناصر عمل موثقة."
            )
            return {
                "status": "needs_clarification",
                "intent": intent or Intent.PERSONAL_CHAT,
                "source": "local_project_knowledge",
                "text": (
                    "حددت أن السؤال عن حالة مشروع CyberLab Agent، لكن لا توجد "
                    "بيانات محلية كافية لإثبات نقطة التوقف أو الخطة الحالية." + detail
                    + " لن أخمّن حالة العمل. يلزم تحديث roadmap.json أو session_state.json "
                    "بآخر خطوة مؤكدة."
                ),
                "executed": False,
            }

        lines.append(
            "هذه معلومات من سجل الحالة المحفوظ، وليست إثباتًا على حالة تشغيل لحظية. "
            "إذا كان السجل قديمًا فقد يحتاج إلى تحديث."
        )
        return {
            "status": "success",
            "intent": intent or Intent.PERSONAL_CHAT,
            "source": "local_project_knowledge",
            "text": "\n".join(lines),
            "project_state": state,
            "executed": False,
        }

    @staticmethod
    def _is_bare_confirmation(text: str) -> bool:
        return str(text).strip().casefold() in {
            "نعم", "أجل", "اجل", "بلى", "لا", "كلا",
            "yes", "no",
        }

    @staticmethod
    def _is_explicit_stop_request(text: str) -> bool:
        """Recognize direct conversational stop requests without invoking execution."""
        normalized = " ".join(str(text or "").casefold().split()).strip(" .!؟?")
        return normalized in {
            "توقف", "توقف عن العمل", "توقف عن الشرح", "توقف عن المتابعة",
            "كفى توقف", "stop", "stop working", "stop explaining",
        }

    @classmethod
    def _is_explicit_diagnostic_request(cls, text: str) -> bool:
        """Allow diagnostics only for a direct, unambiguous system request."""
        normalized = cls._normalize_transition_text(text).strip(" .!؟?")
        direct = (
            "شغل التشخيص", "تشغيل التشخيص", "شخص النظام", "شخّص النظام",
            "شخص صحة النظام", "شخّص صحة النظام", "افحص صحة النظام",
            "فحص صحة النظام", "تحقق من صحة النظام", "اختبر صحة النظام",
            "health check",
        )
        direct_question = {
            "هل النظام سليم", "هل النظام يعمل", "هل النظام يعمل بشكل سليم",
            "ما حالة النظام",
        }
        return normalized in direct_question or any(marker in normalized for marker in direct)

    @staticmethod
    def _explicit_resume_topic(text: str) -> str | None:
        """Extract an explicit resume subject without altering its spelling."""
        value = str(text or "").strip()
        match = re.match(
            r"^(?:(?:حسنا|حسنًا|تمام|طيب)\s+)?"
            r"(?:[اأإآ]?كمل|كمل|تابع|واصل|استكمل|إستكمل|لنواصل|لنكمل)\s+"
            r"(?:الحديث|الحوار|النقاش|الكلام)\s+"
            r"(?:عن|حول)\s+(?:موضوع\s+)?(.+?)\s*$",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        topic = match.group(1).strip(" \t\r\n.,،؛:!?؟")
        return topic or None

    @staticmethod
    def _explicit_dialogue_topic(text: str) -> str | None:
        """Extract the subject of an explicit independent dialogue opening."""
        import re

        value = str(text or "").strip()
        match = re.match(
            r"^\s*(?:دعنا|خلينا|هيا|لن)\s+"
            r"(?:نتحدث|نتكلم|نناقش|نتحاور)\s+(?:عن|حول)\s+"
            r"(.+?)\s*[.!؟?،]*\s*$",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            # A compact topic declaration ("موضوع الرسم والنحت") opens a
            # dialogue branch; it is not merely a noun phrase to explain anew.
            match = re.match(
                r"^\s*(?:موضوع|فكرة)\s+(?!السابق\b|السابقه\b|الرئيسي\b|الرئيسيه\b)(.+?)\s*[.!؟?،]*\s*$",
                value,
                flags=re.IGNORECASE,
            )
        if not match:
            # Natural dialogue commonly declares a subject as "عن موضوع X" or
            # simply "عن X". Exclude retrospective references so they remain
            # owned by the history/restore path.
            match = re.match(
                r"^\s*(?:مثلا\s+)?(?:عن|حول)\s+(?:موضوع\s+)?(.+?)\s*[.!؟?،]*\s*$",
                value,
                flags=re.IGNORECASE,
            )
            if match and any(marker in match.group(1).casefold() for marker in (
                "السابق", "قبل", "كنا", "نتحدث", "تحدثنا", "الموضوع الذي",
            )):
                match = None
        if not match:
            # A short noun list can be the continuation of a friendly topic,
            # not an instruction to execute or explain a new task.
            normalized = value.casefold()
            if any(marker in normalized for marker in ("فن", "رسم", "نحت", "نقش")) and not any(
                marker in normalized for marker in ("اشرح", "وضح", "نفذ", "شغل", "؟", "?")
            ):
                return value.strip(" \t\r\n.,،؛:!?؟")
        if not match:
            # Topic changes are often phrased as "let's move to X", not as
            # "let's talk about X". Treat the subject as dialogue unless a
            # later operational cue explicitly claims it.
            match = re.match(
                r"^\s*(?:حسنا\s+)?(?:دعنا|خلينا)?\s*(?:لننتقل|ننتقل|انتقل)\s+"
                r"(?:(?:الى|إلى)\s+|ل)(?:موضوع\s+)?(.+?)\s*[.!؟?،]*\s*$",
                value,
                flags=re.IGNORECASE,
            )
        if not match:
            return None
        subject = match.group(1).strip(" \t\r\n.,،؛:!?؟")
        subject = re.sub(r"^(?:مفهوم|موضوع|فكرة)\s+", "", subject).strip()
        return subject or None

    @staticmethod
    def _explicit_explanation_topic(text: str) -> str | None:
        """Extract an explicit explain/define request, not a resume reference."""
        import re

        value = str(text or "").strip()
        if any(marker in value.casefold() for marker in (
            "ارجع", "نرجع", "عد إلى", "عد الى", "اكمل", "أكمل",
            "استكمل", "تابع", "واصل", "continue", "resume",
        )):
            return None
        normalized_value = value.casefold()
        if any(marker in normalized_value for marker in (
            "عرف عن نفسك", "عرّف عن نفسك", "اشرح معمارية المشروع",
            "اشرح بنية المشروع", "اشرح بنية النظام",
        )):
            return None
        match = re.match(
            r"^\s*(?:اشرح|شرح|وضح|عرّف|عرف|explain|describe)\s+"
            r"(.+?)\s*[.!؟?،]*\s*$",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        subject = match.group(1).strip(" \t\r\n.,،؛:!?؟")
        subject = re.split(
            r"\s+(?=بالتفصيل|باختصار|بأسلوب(?:\s|$)|بصيغة(?:\s|$)|بشكل(?:\s|$)|أكاديمي(?:\s|$)|رسمي(?:\s|$)|ثم(?:\s|$)|وتوقف|توقف|و(?:\s|$))",
            subject,
            maxsplit=1,
        )[0].strip()
        # Short elaboration phrases are contextual references, not new topics.
        if subject.casefold().strip() in {
            "اكثر", "أكثر", "المزيد", "تفصيل اكثر", "تفصيل أكثر",
            "مزيد من التفاصيل", "more", "more detail", "further",
        }:
            return None
        normalized_subject = ConversationManager._normalize_transition_text(subject)
        if normalized_subject in {
            "هذا", "هذه", "ذلك", "تلك", "هذا الامر", "ذلك الامر",
            "لي هذا", "لي هذه", "عن هذا", "عن هذه",
        }:
            return None
        if any(marker in normalized_subject for marker in (
            "المشروع", "معماريه المشروع", "بنيه المشروع", "بنيه النظام",
        )):
            return None
        return subject or None

    def _pending_confirmation_intent(self, text: str):
        """Resolve bare confirmations only against an explicit pending operation."""
        if not self._is_bare_confirmation(text):
            return None
        context = getattr(self.orchestrator, "context", None)
        last_result = getattr(context, "last_result", None) if context else None
        last_result = last_result if isinstance(last_result, dict) else {}
        pending = last_result.get("pending_confirmation")
        if not pending and last_result.get("pending_save"):
            pending = {"kind": "save_kb"}
        if isinstance(pending, str):
            pending = {"kind": pending}
        if not isinstance(pending, dict):
            return None
        affirmative = str(text).strip().casefold() not in {"لا", "كلا", "no"}
        kind = pending.get("kind")
        if kind == "save_kb":
            return Intent.SAVE_KB if affirmative else Intent.SKIP_KB
        if kind == "resume":
            return Intent.RESUME if affirmative else Intent.CANCEL
        return None

    def _clear_unrelated_execution_file(self, transition, parsed):
        """Do not let an old execution file become a new generic question target."""
        if transition != ContextTransition.NEW_INDEPENDENT:
            return
        if (parsed or {}).get("intent") in {
            Intent.MODIFY_CODE,
            Intent.MODIFY_FILE,
            Intent.GENERATE_CODE,
        }:
            return
        context = getattr(self.orchestrator, "context", None)
        if context is not None:
            context.current_file = None

    @staticmethod
    def _bound_agent_self_reply(
        reply: str,
        intent,
        user_input: str,
        fallback: str = "",
    ) -> str:
        """Enforce concise non-architectural replies for identity/capability questions."""
        value = str(getattr(intent, "value", intent) or "").casefold()
        if value not in {"agent_identity", "agent_capabilities"}:
            return str(reply or "").strip()

        normalized = normalize_text(str(user_input or ""))
        normalized_reply = normalize_text(str(reply or ""))
        if value in {"agent_identity", "agent_capabilities"} and any(marker in normalized_reply for marker in (
            "chatgpt", "openai", "شات جي بي تي", "تشات جي بي تي",
            "سياسات openai", "سياسات الخصوصيه",
        )):
            # The local agent identity is source-backed. Do not let a provider
            # replace it with the host product's identity or policy language.
            return str(fallback or "").strip() or (
                "أنا CyberLab Agent داخل هذا المشروع. أجيب عن هويتي ووظائفي "
                "استنادًا إلى الشفرة المحلية، ولا أقدّم نفسي بوصف ChatGPT."
            )
        no_internals = any(marker in normalized for marker in (
            "لا تعرض بنية", "ليس تعرض بنية", "لا تشرح بنية",
            "لا تعرض تفاصيل المشروع", "لا تذكر الملفات",
            "لا تعرض هيكل", "بشكل ودي", "ببساطة", "بشكل بسيط",
        ))
        asks_for_explicit_architecture = not no_internals and any(
            marker in normalized for marker in (
                "المكونات البرمجية", "الطبقات", "المعمارية", "البنية البرمجية",
                "مسار التنفيذ", "اسماء الملفات", "أسماء الملفات",
                "preparedexecutionrequest", "eventloop",
            )
        )
        internal_pattern = re.compile(
            r"(?:lab_v4_dev/|(?:[A-Za-z_][\w.-]*/)+[A-Za-z_][\w.-]*"
            r"|\b(?:PreparedExecutionRequest|EventLoop|ConversationManager|"
            r"DialogueMemory|MemoryStore|ContextStore|Orchestrator|gateway_ask)\b"
            r"|\b[A-Za-z_][A-Za-z0-9_]*\.py\b)",
            re.IGNORECASE,
        )

        pieces = [
            re.sub(r"^\s*(?:[-*•]+\s*|\d+[.)、]\s*)", "", part).strip()
            for part in re.split(r"(?<=[.!؟?])\s+|\n+", str(reply or "").strip())
        ]
        pieces = [
            part for part in pieces
            if part and (asks_for_explicit_architecture or not internal_pattern.search(part))
        ]
        max_pieces = 5 if asks_for_explicit_architecture else 3
        max_chars = 900 if asks_for_explicit_architecture else 620
        bounded = []
        length = 0
        for part in pieces:
            separator_length = 1 if bounded else 0
            if len(bounded) >= max_pieces or length + separator_length + len(part) > max_chars:
                break
            bounded.append(part)
            length += separator_length + len(part)

        result = " ".join(bounded).strip()
        if result:
            return result
        return str(fallback or "").strip() or (
            "أنا CyberLab Agent. أساعدك في فهم طلبك وتحديد الخطوة المناسبة، "
            "وأوضّح حدود ما أستطيع فعله بدل الادعاء بقدرات غير متاحة."
        )

    @staticmethod
    def _is_fragmentary_turn(text: str) -> bool:
        """Reject isolated letters/unknown two-letter fragments before context inheritance."""
        normalized = normalize_text(str(text or ""))
        compact = "".join(
            char for char in normalized
            if char.isalnum() or "\u0600" <= char <= "\u06ff"
        ).strip()
        if not compact:
            return False
        if len(compact) == 1:
            return True
        if len(compact) != 2:
            return False
        # These are valid short Arabic words/particles; leave their normal
        # conversational and clarification routes intact.
        common_short_words = {
            "لا", "ما", "من", "في", "عن", "هل", "هو", "هي", "كم", "كل",
            "لم", "لن", "قد", "بل", "يا", "مع", "به", "له", "هم", "هن",
            "اي", "اذ", "ثم",
        }
        return compact not in common_short_words and all(
            "\u0600" <= char <= "\u06ff" for char in compact
        )

    @staticmethod
    def _is_new_dialogue_session_request(text: str) -> bool:
        """Recognize explicit natural-language requests to start an isolated dialogue."""
        normalized = " ".join(
            str(text or "").casefold()
            .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ـ", "")
            .strip(" .,،؛:!?؟'()[]{}")
            .split()
        )
        exact = {
            "جلسة جديدة", "جلسه جديده", "new session", "ابدأ جلسة جديدة",
            "ابدا جلسه جديده", "ابدأ حوارا جديدا", "ابدا حوارا جديدا",
            "بدء جلسة جديدة", "بدء حوار جديد",
        }
        if normalized in exact:
            return True
        explicit_starts = (
            "اريد بدء جلسة حوار جديدة",
            "اريد بدء جلسه حوار جديده",
            "اريد بدء جلسة جديدة ومستقلة",
            "اريد بدء حوار جديد ومستقل",
            "ابدأ جلسة حوار جديدة",
            "ابدا جلسه حوار جديده",
            "انشئ جلسة حوار جديدة",
            "انشئ جلسه حوار جديده",
            "ابدأ جلسة جديدة ومستقلة",
            "ابدا جلسه جديده ومستقله",
        )
        if any(normalized.startswith(prefix) for prefix in explicit_starts):
            return True

        # Spoken examples and discourse-prefixed requests still express a real
        # session boundary ("قلت نبدا حوار ودي جديد مثلا"). Detect the semantic
        # combination rather than requiring the request to start with a template.
        tokens = set(normalized.split())
        has_dialogue_object = bool(tokens & {
            "جلسة", "جلسه", "حوار", "محادثة", "محادثه", "دردشة", "دردشه", "حديث",
        })
        has_new_marker = bool(tokens & {
            "جديد", "جديدة", "جديده", "جديدا", "مستقل", "مستقلة", "مستقله",
        }) or "من جديد" in normalized
        has_start_marker = bool(tokens & {
            "ابدأ", "ابدا", "نبدا", "نبدأ", "لنبدأ", "لنبدأ", "بدء",
            "انشئ", "انشاء", "خلينا", "نفتح", "نبدأ", "ننشئ",
        })
        return has_dialogue_object and has_new_marker and has_start_marker



    @staticmethod
    def _is_current_project_identity_request(text: str) -> bool:
        normalized = normalize_text(str(text or ""))
        # The project name must immediately follow an identity predicate.
        # This intentionally excludes broader questions such as project plans,
        # architecture, and agent limits that merely mention CyberLab Agent.
        return bool(re.search(
            r"(?:^|\s)(?:ماهو|ما هو|ماهي|ما هي|عرف|ما طبيعة)\s+"
            r"(?:(?:مشروع|المشروع|الوكيل)\s+)?cyberlab(?:[_ -]?agent)\b",
            normalized,
        ))

    @staticmethod
    def _local_current_project_identity_answer() -> dict:
        """Describe this checkout's project from its local project-state record."""
        try:
            from lab_v4_dev.awareness.project_knowledge import get_project_state
            state = get_project_state()
        except Exception as exc:
            return {
                "status": "needs_clarification",
                "intent": Intent.CYBER_EXPLAIN,
                "source": "local_project_identity",
                "executed": False,
                "text": f"لم أتمكن من قراءة سجل تعريف المشروع المحلي ({type(exc).__name__})؛ لن أستبدله بوصف عام أو تخميني.",
            }
        state = state if isinstance(state, dict) else {}
        lines = [
            "CyberLab Agent هو المشروع البرمجي الموجود في هذا المستودع والذي نعمل على تطويره؛ وليس وصفًا عامًا لمختبر تدريب اختراق.",
            "ملامح المشروع المثبتة في سجل الحالة المحلي:",
        ]
        fields = (
            ("version", "الإصدار"),
            ("current_focus", "محور التطوير الحالي"),
            ("last_goal", "آخر هدف عمل مسجل"),
            ("last_step", "الخطوة التالية المسجلة"),
        )
        for key, label in fields:
            value = str(state.get(key) or "").strip()
            if value and value not in {"?", "unknown", "غير معروف", "غير متاح"}:
                lines.append(f"- {label}: {value}")
        for key, label in (("active", "عناصر العمل النشطة"), ("planned", "العناصر المخططة")):
            values = [str(value).strip() for value in (state.get(key) or []) if str(value).strip()]
            if values:
                lines.append(f"- {label}: " + "؛ ".join(values[:5]))
        if state.get("completed_count") is not None:
            lines.append(f"- العناصر المكتملة المسجلة: {state['completed_count']}")
        if len(lines) == 2:
            lines.append("لم يوفر سجل الحالة الحالي تفاصيل إضافية كافية عن التركيز أو التقدم.")
        return {
            "status": "success",
            "intent": Intent.CYBER_EXPLAIN,
            "source": "local_project_identity",
            "executed": False,
            "text": "\n".join(lines),
        }

    @staticmethod
    def _is_memory_inventory_request(text: str) -> bool:
        """Recognize broad requests to inspect the agent's locally persisted memory."""
        normalized = ConversationManager._normalize_transition_text(text)
        memory_cues = (
            "تتذكر", "اتذكر", "تذكره", "ذاكره", "ذاكرة",
            "محفوظ", "المحفوظ", "تعرفه", "اعرفه",
        )
        broad_scope = (
            "كل شيء", "كل شي", "كل ما", "جميع ما",
            "منذ البدايه", "من البدايه", "من خلال كل",
            "كل المعلومات", "كل ما تعرفه", "كل ما هو محفوظ",
        )
        return (
            any(marker in normalized for marker in memory_cues)
            and any(marker in normalized for marker in broad_scope)
        )

    def _local_memory_inventory_answer(self) -> dict:
        """Read local memory owners and report their contents without a provider."""
        lines = ["ملخص الذاكرة المحلية المتاحة في CyberLab Agent:"]
        session_count = 0
        session_type_counts = {"dialogue": 0, "work": 0, "other": 0}
        recent_summaries = []
        try:
            from lab_v4_dev.memory.session_state import (
                get_session_index,
                get_recent_sessions,
                get_session_by_id,
                get_session_type_counts,
                build_session_brief_summary,
            )
            index = get_session_index()
            counts = get_session_type_counts()
            session_count = counts["total"]
            session_type_counts = {
                "dialogue": counts["dialogue"],
                "work": counts["work"],
                "other": counts["other"],
            }
            for item in get_recent_sessions()[:5]:
                session_id = str(item.get("session_id") or "")
                detail = get_session_by_id(session_id) if session_id else {}
                brief = build_session_brief_summary(detail or item)
                topic = str(brief.get("topic") or "جلسة بلا عنوان موثوق").strip()
                summary = str(brief.get("summary") or "").strip()
                recent_summaries.append((topic, summary, brief.get("session_type")))
        except Exception:
            index = []

        lines.append(
            f"- الجلسات المحفوظة: {session_count} "
            f"(حوارات: {session_type_counts['dialogue']}، "
            f"عمل: {session_type_counts['work']}، "
            f"غير مصنفة: {session_type_counts['other']})."
        )
        if recent_summaries:
            lines.append("- أحدث الجلسات المحفوظة ومضمونها:")
            for topic, summary, _kind in recent_summaries:
                lines.append(f"  • {topic}: {summary or 'لا تتوفر تفاصيل كافية في سجل الجلسة.'}")

        # The live dialogue is a separate owner from persisted sessions.
        try:
            state = getattr(self.dialogue_memory, "state", None)
            live_exchanges = list(getattr(state, "exchange_archive", []) or [])
            session_id = str(getattr(state, "session_id", "") or "")
            live_exchanges = [
                item for item in live_exchanges
                if isinstance(item, dict)
                and (not session_id or str(item.get("session_id") or "") == session_id)
                and str(item.get("context_kind") or "").casefold()
                    not in {"work", "system", "execution"}
                and str(item.get("conversation_domain") or "").casefold()
                    not in {"work", "system", "execution"}
            ]
            from lab_v4_dev.memory.session_state import summarize_dialogue_exchanges
            live_report = summarize_dialogue_exchanges(
                live_exchanges,
                topic=str(getattr(state, "last_topic", "") or ""),
                limit=3,
            )
            if live_report["exchange_count"]:
                lines.append("- الحوار الجاري (منفصل عن الجلسات المحفوظة):")
                if live_report["meaningful_exchange_count"]:
                    lines.append(f"  • الموضوع: {live_report['topic'] or 'غير محدد'}.")
                    lines.extend(f"  • {item}" for item in live_report["insights"][:3])
                    lines.append(f"  • نقطة التوقف: {live_report['stop_point']}")
                else:
                    lines.append("  • سجل حالي يقتصر على التحية والتعارف، دون موضوع نقاش فعلي.")
        except Exception:
            lines.append("- تعذر قراءة سجل الحوار الجاري في هذه المحاولة.")

        # Project Knowledge is not the dialogue archive or the execution context.
        try:
            from lab_v4_dev.awareness import project_knowledge
            project_state = project_knowledge.get_project_state()
            project_facts = []
            version = str(project_state.get("version") or "").strip()
            focus = str(project_state.get("current_focus") or "").strip()
            last_goal = str(project_state.get("last_goal") or "").strip()
            last_step = str(project_state.get("last_step") or "").strip()
            if version and version != "?":
                project_facts.append(f"الإصدار المسجل: {version}")
            if focus and focus != "?":
                project_facts.append(f"التركيز الحالي: {focus}")
            if project_state.get("completed_count") is not None:
                project_facts.append(f"عدد العناصر المكتملة المسجلة: {project_state['completed_count']}")
            if last_goal and last_goal != "?":
                project_facts.append(f"آخر هدف عمل محفوظ: {last_goal}")
            if last_step and last_step != "?":
                project_facts.append(f"الخطوة التالية المسجلة: {last_step}")
            active = [str(value).strip() for value in (project_state.get("active") or []) if str(value).strip()]
            planned = [str(value).strip() for value in (project_state.get("planned") or []) if str(value).strip()]
            if active:
                project_facts.append("عناصر العمل النشطة: " + "؛ ".join(active[:4]))
            if planned:
                project_facts.append("العناصر المخططة: " + "؛ ".join(planned[:4]))
            if project_facts:
                lines.append("- معرفة المشروع المحفوظة:")
                lines.extend(f"  • {fact}" for fact in project_facts)
        except Exception:
            lines.append("- تعذر قراءة Project Knowledge في هذه المحاولة.")

        # MemoryStore owns task history and lessons, not dialogue or project knowledge.
        agent = getattr(self.orchestrator, "agent", None)
        memory = getattr(agent, "memory", None)
        if memory is not None:
            try:
                counts = memory.task_status_counts()
                lessons = memory.all_lessons()
                if counts or lessons:
                    lines.append("- سجل المهام والدروس:")
                    if counts:
                        lines.append(f"  • حالات المهام المسجلة: {counts}")
                    lines.append(f"  • عدد الدروس المحفوظة: {len(lessons or [])}")
            except Exception:
                lines.append("- تعذر قراءة سجل المهام والدروس في هذه المحاولة.")

        lines.append(
            "هذه قراءة لمصادر محلية محددة؛ لا تعني أن كل محتوى كل جلسة قد عُرض هنا. "
            "يمكن استخراج تقرير مستقل لأي جلسة برقمها، أو عرض ملخصات جميع الجلسات."
        )
        return {
            "status": "success",
            "intent": Intent.MEMORY_DUMP,
            "source": "local_memory_inventory",
            "text": "\n".join(lines),
            "executed": False,
            "memory_sources": [
                "saved_sessions", "live_dialogue", "project_knowledge", "task_history",
            ],
        }
    @staticmethod
    def _continue_saved_dialogue(text: str, session_id: str) -> dict | None:
        """Continue one saved dialogue without importing it into live memory."""
        from lab_v4_dev.memory.session_state import (
            _dialogue_exchanges, _dialogue_exchange_subject,
            _is_dialogue_control_text, get_session_by_id,
        )

        saved = get_session_by_id(session_id)
        if (
            not isinstance(saved, dict)
            or str(saved.get("session_id") or "").strip() != str(session_id).strip()
            or str(saved.get("session_type") or "").casefold() != "dialogue"
        ):
            return None
        exchanges = _dialogue_exchanges(saved)
        meaningful = [
            item for item in exchanges
            if not item.get("recall_only")
            and not item.get("state_boundary_only")
            and not _is_dialogue_control_text(item.get("user"))
        ]
        if not meaningful:
            return None

        dialogue = saved.get("dialogue_state") or {}
        stored_topic = str(dialogue.get("last_topic") or "").strip() if isinstance(dialogue, dict) else ""
        topic = stored_topic if stored_topic and not _is_dialogue_control_text(stored_topic) else ""
        if not topic:
            topic = next(
                (_dialogue_exchange_subject(item) for item in reversed(meaningful) if _dialogue_exchange_subject(item)),
                "",
            )
        latest = meaningful[-1]
        domain = str(latest.get("conversation_domain") or "general").casefold()
        if domain in {"project", "work", "system", "execution"}:
            return None
        if domain not in {"general", "social", "technical"}:
            domain = "general"

        history = []
        for exchange in meaningful:
            exchange_domain = str(exchange.get("conversation_domain") or domain).casefold()
            exchange_kind = str(exchange.get("context_kind") or "dialogue").casefold()
            for role, key in (("user", "user"), ("assistant", "assistant")):
                value = str(exchange.get(key) or "").strip()
                if value:
                    history.append({
                        "role": role, "content": value, "target": exchange.get("target"),
                        "context_kind": exchange_kind, "conversation_domain": exchange_domain,
                        "session_id": session_id,
                    })

        parsed = {
            "intent": Intent.PERSONAL_CHAT, "target": topic,
            "entity_type": "CONCEPT" if topic else "REFERENCE",
            "conversation_domain": domain,
            "conversation_act": "CONVERSATION_CONTINUATION",
            "response_attributes": {"dialogue_recovery": "saved_session_continuation"},
        }
        semantic = {
            "intent": "personal_chat", "target": topic,
            "conversation_domain": domain,
            "conversation_act": "CONVERSATION_CONTINUATION",
            "context_kind": "dialogue",
        }
        result = answer_local_response(text, parsed, semantic, history=history)
        if not isinstance(result, dict):
            return None
        result = dict(result)
        result.update({
            "status": "success", "source": "saved_dialogue_local_continuation",
            "session_id": session_id, "output_kind": "continue_topic",
            "evidence_scope": "saved_session",
            "context_action": "saved_session_followup", "executed": False,
        })
        return result

    def _attach_route_decision(self, result: dict, decision: RouteDecision) -> dict:
        """Make a previously finalized decision govern a direct response."""
        result = dict(result or {})
        result["route_decision"] = decision
        result.setdefault(
            "executed",
            decision.route in {"L-EXEC", "P-TOOL"}
            and result.get("status") not in {
                "needs_clarification", "denied", "unsupported", "error", "failed",
            },
        )
        self.context_lock = decision.context_lock
        if decision.output_kind != "none":
            result["output_kind"] = decision.output_kind
        elif decision.route == "L-SESSION":
            result.pop("output_kind", None)
        return result

    def _finalize_direct_result(
        self,
        result: dict,
        *,
        intent,
        route: str,
        selected_session: dict | None = None,
        saved_session_request: bool = False,
        selected_saved_session_id: str | None = None,
    ) -> dict:
        """Attach the same immutable route contract to safe early responses."""
        decision = self.finalize_route(
            parsed={"intent": intent, "confidence": 1.0},
            selected_session=selected_session or {"kind": "none"},
            saved_session_request=saved_session_request,
            selected_saved_session_id=selected_saved_session_id,
            transition=ContextTransition.NEW_INDEPENDENT,
            route_override=route,
        )
        return self._attach_route_decision(result, decision)

    def process(self, user_input: str, *, _restore_context: dict | None = None) -> dict:
        # Session boundaries take precedence over pending clarifications and all
        # NLU/context resolution. A new dialogue must never inherit old state.
        if self._is_new_dialogue_session_request(user_input):
            self.active_report_session_id = None
            self.active_report_topic_filter = None
            self.active_live_output_kind = None
            self.context_lock = ContextLock()
            reset = getattr(self.orchestrator, "reset_conversation_context", None)
            if callable(reset):
                reset()
            else:
                agent = getattr(self.orchestrator, "agent", None)
                reset = getattr(agent, "reset_conversation_context", None)
                if callable(reset):
                    reset()
            memory_reset = getattr(self.dialogue_memory, "reset", None)
            if callable(memory_reset):
                memory_reset()
            return self._finalize_direct_result({
                "status": "success",
                "intent": Intent.RESTART,
                "source": "conversation_manager",
                "text": "بدأت جلسة حوار جديدة ومستقلة. لم يتم إنشاء أو تنفيذ أي مهمة، ولم أستعد سياق الجلسة السابقة.",
                "executed": False,
            }, intent=Intent.RESTART, route="L-SOCIAL")

        selected_saved_session_id = None
        pending_saved_session_selection = {}
        active_report_followup = False
        active_report_continue = False
        # ContextLock is the durable owner contract for saved-report follow-ups;
        # the legacy scalar remains a compatibility mirror, not the authority.
        locked_report_id = (
            str(self.context_lock.session_id or "").strip()
            if self.context_lock.active
            and self.context_lock.reason == "saved_session_selection"
            else ""
        )
        active_report_id = str(self.active_report_session_id or locked_report_id).strip()
        if active_report_id:
            from lab_v4_dev.memory.session_state import session_route_contract
            explicit_session_selector = session_route_contract(user_input)
            normalized_followup = normalize_text(user_input)
            followup_references_active_report = any(marker in normalized_followup for marker in (
                "ذلك الحوار", "ذلك النقاش", "الجلسة المحفوظة الخاصة بذلك الحوار",
            ))
            active_report_followup = (
                (
                    explicit_session_selector.get("kind") == "none"
                    or followup_references_active_report
                )
                and any(marker in normalized_followup for marker in (
                    "اختصر", "اختصار", "لخص", "تلخيص", "ملخص",
                    "بسط", "بشكل مبسط", "بطريقه مبسطه", "بطريقة مبسطة",
                    "اشرح", "وضح", "ما علاقه", "ما علاقة", "كيف يرتبط",
                    "ماذا عن", "تقرير", "تقريرا", "تقريرًا",
                    "الموضوعات", "موضوعات", "الافكار", "الأفكار",
                    "ماذا ناقشنا", "ما ناقشنا", "النتائج", "النقاط المتبقية",
                    "ذلك الحوار", "هذا الحوار", "الحوار السابق", "ذلك النقاش",
                    "اكمل", "استكمل", "تابع", "واصل", "من نفس النقطة",
                    "نقطة التوقف", "استئناف الحوار",
                ))
            )
            active_report_continue = active_report_followup and any(
                marker in normalized_followup for marker in (
                    "اكمل", "استكمل", "تابع", "واصل", "من نفس النقطة",
                    "نقطة التوقف", "استئناف الحوار",
                )
            )
            if active_report_followup:
                selected_saved_session_id = active_report_id
            elif explicit_session_selector.get("kind") == "none":
                # An unrelated new request releases the report lock. Explicit
                # saved-session selection will replace it after resolution.
                self.active_report_session_id = None
                self.active_report_topic_filter = None
                if self.context_lock.reason == "saved_session_selection":
                    self.context_lock = ContextLock()

        # Resolve saved-session ambiguity before NLU sees this turn.
        if self.dialogue_memory:
            state = getattr(self.dialogue_memory, "state", None)
            pending = getattr(state, "pending_clarification", None)
            if isinstance(pending, dict) and pending.get("kind") == "saved_session_choice":
                pending_saved_session_selection = dict(pending)
                from lab_v4_dev.memory.session_state import resolve_saved_session_choice
                candidates = pending.get("candidates") or []
                selected_saved_session_id = resolve_saved_session_choice(user_input, candidates)
                if selected_saved_session_id:
                    state.pending_clarification = None
                else:
                    normalized_choice = self._normalize_transition_text(user_input)
                    refers_to_saved_session = any(marker in normalized_choice for marker in (
                        "جلسة", "جلسه", "ملخص", "ملخصات", "لخص", "تلخيص",
                        "تقرير", "استرجع", "استعد", "هذه", "التي عرضتها",
                        "اختصر", "اكمل", "الفن", "الرسم", "النحت", "النقش",
                    ))
                    if refers_to_saved_session:
                        lines = [
                            "لم أحدد جلسة واحدة بعد؛ لن أختار جلسة مختلفة بالتخمين.",
                            "اختر رقم الخيار الظاهر أو أرسل معرّف الجلسة:",
                        ]
                        for number, item in enumerate(candidates, 1):
                            title = str(item.get("title") or item.get("topic") or "جلسة بلا عنوان")
                            session_id = str(item.get("session_id") or "?")
                            lines.append(f"- الخيار {number}: {title} [{session_id}]")
                            if item.get("summary"):
                                lines.append(f"  الملخص: {item['summary']}")
                        return self._finalize_direct_result({
                            "status": "needs_clarification",
                            "intent": Intent.SESSION_RESTORE,
                            "source": "saved_session_selector",
                            "executed": False,
                            "text": "\n".join(lines),
                        }, intent=Intent.SESSION_RESTORE, route="L-SESSION",
                           selected_session={"kind": "collection"})
                    state.pending_clarification = None

            # Preserve project-list ordering clarification behavior.
            pending = getattr(state, "pending_clarification", None)
            if isinstance(pending, dict) and pending.get("kind") == "project_order":
                choice = str(user_input).strip()
                orders = {
                    "1": "حسب ترتيب العمل عليها",
                    "2": "أبجديًا",
                    "3": "حسب الحجم",
                }
                order = orders.get(choice)
                if order:
                    base_request = str(pending.get("request", "")).strip()
                    state.pending_clarification = None
                    user_input = f"{base_request} {order}".strip()

        mode = detect_mode(user_input)
        # A direct stop request is a conversation control, not an executable
        # task. Do not send it through the parser fallback or Orchestrator.
        if self._is_explicit_stop_request(user_input):
            return self._finalize_direct_result({
                "status": "success",
                "intent": Intent.STOP,
                "source": "conversation_manager",
                "text": "سأتوقف عن متابعة الطلب الحالي؛ لم أرسل أمر إلغاء إلى أي مهمة تنفيذية.",
                "executed": False,
            }, intent=Intent.STOP, route="L-SOCIAL")

        # Incomplete fragments must not inherit a prior continuation act or
        # stale target. Asking for the missing text is read-only: do not append
        # it to dialogue history, update the active topic, or call a provider.
        if self._is_fragmentary_turn(user_input):
            return self._finalize_direct_result({
                "status": "needs_clarification",
                "intent": Intent.PERSONAL_CHAT,
                "source": "conversation_manager",
                "text": (
                    "وصلتني رسالة قصيرة أو مبتورة ولم يتضح المقصود منها. "
                    "اكتب الفكرة كاملة أو وضّح ما تريد متابعته."
                ),
                "executed": False,
            }, intent=Intent.PERSONAL_CHAT, route="CLARIFY")

        # Parse the current turn without any persistent NLU context first.
        # The transition decision below is the sole authority that may grant
        # the active DialogueMemory topic to a second canonical parse.
        confirmation_intent = self._pending_confirmation_intent(user_input)
        candidate = (
            {
                "intent": confirmation_intent,
                "target": "",
                "context": "general",
                "confidence": 1.0,
                "raw": user_input,
                "source": "pending_confirmation",
                "entity_type": "CONFIRMATION",
                "semantic_pattern": "PENDING_CONFIRMATION",
            }
            if confirmation_intent is not None
            else self._safe_parse(self._correct_contextual_dialogue_typos(user_input))
        )
        if _restore_context:
            candidate = {
                "intent": Intent.PERSONAL_CHAT,
                "target": str(_restore_context.get("entity") or "").strip(),
                "context": "general",
                "confidence": 1.0,
                "raw": user_input,
                "source": "authorized_dialogue_restore",
                "entity_type": _restore_context.get("entity_type", "CONCEPT"),
                "conversation_domain": _restore_context.get("conversation_domain", "general"),
                "conversation_act": "TOPIC_RETURN",
                "conversation_confidence": 1.0,
                "response_attributes": {"dialogue_recovery": "named_topic_return"},
                "semantic_pattern": "AUTHORIZED_DIALOGUE_RESTORE",
            }
        normalized_command = " ".join(
            str(user_input or "").casefold()
            .replace("أ", "ا").replace("إ", "ا")
            .strip(" \t\r\n.,،؛:!?؟")
            .split()
        )
        if normalized_command in {
            "تحقق", "تحقق اولا", "تحقق من فضلك", "تحقق اولا من فضلك",
            "verify", "verify first",
        } and not str(candidate.get("target") or "").strip():
            return self._finalize_direct_result({
                "status": "needs_clarification",
                "intent": Intent.VERIFY_FIX,
                "source": "conversation_manager",
                "text": (
                    "ما الذي تريدني أن أتحقق منه تحديدًا؟ "
                    "اذكر الإصلاح أو الاختبار أو المعلومة المقصودة."
                ),
                "executed": False,
            }, intent=Intent.VERIFY_FIX, route="CLARIFY")

        if confirmation_intent is None and self._is_bare_confirmation(user_input):
            # A bare yes/no without a pending operation is dialogue, not a new
            # executable intent and not a reason to overwrite the active topic.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": "social",
                "conversation_act": "SOCIAL_ACKNOWLEDGEMENT",
                "conversation_confidence": 0.90,
                "response_attributes": {},
                "semantic_pattern": "BARE_CONFIRMATION_NO_PENDING",
                "source": "bare_confirmation",
            })
        # `parse()` is the single semantic interpretation boundary for this
        # turn.  Do not classify the same text again here: a second semantic
        # pass can disagree with the canonical parse and let a later branch
        # steal ownership of the response.
        raw_signal = self._semantic_signal_from_parsed(candidate)
        semantic_interrupted_recovery = str(
            (raw_signal.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold() == "interrupted_branch"
        from lab_v4_dev.memory.session_state import session_route_contract
        selected_session = session_route_contract(user_input)
        if (
            selected_session.get("kind") == "list"
            and selected_session.get("report_mode") == "full"
        ):
            selected_session["output_kind"] = "report"
        if (
            selected_session.get("kind") in {"none", "reference"}
            and self._is_current_project_identity_request(user_input)
        ):
            result = self._local_current_project_identity_answer()
            decision = self.finalize_route(
                parsed={"intent": Intent.CYBER_EXPLAIN, "conversation_domain": "project"},
                selected_session={"kind": "none"},
                saved_session_request=False,
                selected_saved_session_id=None,
                transition=ContextTransition.NEW_INDEPENDENT,
            )
            return self._attach_route_decision(result, decision)

        normalized_repeated_topic_query = normalize_text(user_input)
        repeated_topic_request = any(marker in normalized_repeated_topic_query for marker in (
            "اكثر موضوع متكرر", "الموضوع الاكثر تكرارا", "موضوع متكرر",
            "موضوع تكرر", "تكرر في عدة جلسات", "تكرر عبر الجلسات",
        ))
        if repeated_topic_request and selected_session.get("kind") in {"none", "reference"}:
            from lab_v4_dev.memory.session_state import analyze_repeated_dialogue_topics
            repeated_topics = analyze_repeated_dialogue_topics(limit=8)
            lines = ["نتيجة فحص موضوعات جلسات الحوار المحفوظة:"]
            if not repeated_topics:
                lines.append("لم أجد موضوعًا موثقًا في أكثر من جلسة حوار وفق السجلات المتاحة.")
            else:
                for rank, item in enumerate(repeated_topics, 1):
                    lines.append(
                        f"{rank}) {item['topic']} — تكرر في {item['session_count']} جلسات."
                    )
                    for session in item["sessions"]:
                        lines.append(
                            f"   - الجلسة #{session['number']}: {session['title']} "
                            f"[{session['session_id']}]"
                        )
            return self._finalize_direct_result({
                "status": "success", "intent": Intent.MEMORY_DUMP,
                "source": "saved_dialogue_topic_analysis",
                "output_kind": "list", "evidence_scope": "none", "evidence_collection": "saved_dialogues",
                "executed": False, "text": "\n".join(lines),
                "repeated_topics": repeated_topics,
            }, intent=Intent.MEMORY_DUMP, route="L-SESSION",
               selected_session={"kind": "collection", "output_kind": "list"}, saved_session_request=True)

        if active_report_continue and selected_saved_session_id:
            continuation = self._continue_saved_dialogue(
                user_input, selected_saved_session_id,
            )
            if continuation is not None:
                decision = self.finalize_route(
                    parsed={"intent": Intent.PERSONAL_CHAT, "conversation_domain": "general"},
                    selected_session={
                        "kind": "id", "session_id": selected_saved_session_id,
                        "output_kind": "continue_topic",
                    },
                    saved_session_request=True,
                    selected_saved_session_id=selected_saved_session_id,
                    transition=ContextTransition.NEW_INDEPENDENT,
                )
                continuation["route_decision"] = decision
                self.context_lock = decision.context_lock
                self.active_report_session_id = selected_saved_session_id
                return continuation

        if selected_saved_session_id:
            inherited_report_mode = str(
                pending_saved_session_selection.get("report_mode") or ""
            ).strip()
            locked_output_kind = (
                self.context_lock.output_kind
                if self.context_lock.active
                and self.context_lock.reason == "saved_session_selection"
                else None
            )
            inherited_output_kind = str(
                pending_saved_session_selection.get("output_kind") or locked_output_kind or ""
            ).strip()
            inherited_topic_filter = (
                pending_saved_session_selection.get("topic_filter")
                or (
                    self.context_lock.topic
                    if self.context_lock.active
                    and self.context_lock.reason == "saved_session_selection"
                    else None
                )
            )
            selected_session = {
                "kind": "id",
                "session_id": selected_saved_session_id,
                "report_mode": (
                    inherited_report_mode
                    or (
                        "full"
                        if active_report_followup and any(
                            marker in normalize_text(user_input)
                            for marker in ("تقرير", "تقريرا", "تقريرًا")
                        )
                        else "summary" if active_report_followup else "standard"
                    )
                ),
                "output_kind": (
                    inherited_output_kind
                    or (
                        "report"
                        if active_report_followup and any(
                            marker in normalize_text(user_input)
                            for marker in ("تقرير", "تقريرا", "تقريرًا")
                        )
                        else "summary" if active_report_followup else "report"
                    )
                ),
                "topic_filter": (
                    user_input
                    if active_report_followup and any(
                        marker in normalize_text(user_input)
                        for marker in ("ما علاقه", "ما علاقة", "كيف يرتبط")
                    )
                    else (
                        inherited_topic_filter
                        or (
                            self.active_report_topic_filter
                            if active_report_followup
                            else None
                        )
                    )
                ),
            }

        # A numbered saved-dialogue continuation must be resolved and continued
        # from that exact saved record. Do not let the generic live-dialogue
        # continuation path consume it or substitute the current session.
        if (
            selected_session.get("kind") == "number"
            and selected_session.get("output_kind") == "continue_topic"
        ):
            from lab_v4_dev.memory.session_state import get_session_by_number
            numbered = get_session_by_number(selected_session.get("number"))
            saved_id = str((numbered or {}).get("session_id") or "").strip()
            continuation = (
                self._continue_saved_dialogue(user_input, saved_id)
                if saved_id else None
            )
            if continuation is None:
                return self._finalize_direct_result({
                    "status": "needs_clarification",
                    "intent": Intent.SESSION_RESTORE,
                    "source": "saved_dialogue_continuation",
                    "output_kind": "continue_topic",
                    "evidence_scope": "saved_session",
                    "executed": False,
                    "text": (
                        "تعذر استئناف الحوار من سجل الجلسة المحددة؛ "
                        "لم أستخدم الحوار الحالي بديلًا عنها."
                    ),
                }, intent=Intent.SESSION_RESTORE, route="L-SESSION",
                   selected_session={"kind": "number", "number": selected_session.get("number"),
                                     "output_kind": "continue_topic"},
                   saved_session_request=True)
            decision = self.finalize_route(
                parsed={
                    "intent": Intent.PERSONAL_CHAT,
                    "conversation_domain": "general",
                    "output_kind": "continue_topic",
                },
                selected_session={
                    "kind": "id", "session_id": saved_id,
                    "output_kind": "continue_topic",
                },
                saved_session_request=True,
                selected_saved_session_id=saved_id,
                transition=ContextTransition.NEW_INDEPENDENT,
            )
            continuation = self._attach_route_decision(continuation, decision)
            return continuation

        # Every turn receives one local output contract before any response
        # owner runs. Saved-session selection remains separate from live-dialogue
        # rendering, but both share the same output-kind decision.
        candidate = dict(candidate or {})
        candidate["output_kind"] = str(selected_session.get("output_kind") or "chat")
        if selected_session.get("topic_filter"):
            candidate["topic_filter"] = selected_session["topic_filter"]
        if selected_session.get("kind") not in {"none", "reference"}:
            candidate["session_selector"] = dict(selected_session)

        # Capability questions are answered from the local session-store
        # contract. They must not trigger a restore, a transcript, or a provider.
        if selected_session.get("output_kind") == "capability":
            decision = self.finalize_route(
                parsed={"intent": Intent.AGENT_CAPABILITIES, "conversation_domain": "agent_self"},
                selected_session=selected_session,
                saved_session_request=False,
                selected_saved_session_id=None,
                transition=ContextTransition.NEW_INDEPENDENT,
            )
            self.context_lock = decision.context_lock
            return {
                "status": "success",
                "intent": Intent.AGENT_CAPABILITIES,
                "route_decision": decision,
                "source": "local_session_store",
                "output_kind": "capability",
                "executed": False,
                "text": (
                    "نعم، أستطيع تحديد جلسة محفوظة من فهرسها وقراءة سجلها. "
                    "اذكر رقم الجلسة أو معرّفها أو موضوعها؛ ولن أعرض النص الحرفي "
                    "للحوار إلا إذا طلبته صراحة."
                ),
            }

        # Broad memory-inventory questions are read from local memory owners.
        # Explicit saved-session selectors keep their dedicated report path.
        if (
            selected_session.get("kind") == "none"
            and self._is_memory_inventory_request(user_input)
        ):
            return self._finalize_direct_result(
                self._local_memory_inventory_answer(),
                intent=Intent.MEMORY_DUMP, route="L-SESSION",
                selected_session={"kind": "collection", "output_kind": "list"}, saved_session_request=True,
            )

        normalized_session_request = self._normalize_transition_text(user_input).strip(
            " .,،؛:!?؟"
        )
        live_state = getattr(self.dialogue_memory, "state", None)
        live_dialogue_archive = bool(
            self.dialogue_memory
            and (
                getattr(live_state, "exchange_archive", [])
                or getattr(live_state, "history", [])
                or getattr(live_state, "last_topic", None)
            )
        )
        # The session selector is authoritative once it has identified a
        # previous saved dialogue. Reclassifying that decision as live-history
        # retrieval based on missing phrase markers made equivalent questions
        # ("آخر موضوع ناقشناه سابقًا", "ماذا كنا نقول في الجلسة السابقة")
        # select different memory owners. Only the intentionally ambiguous
        # generic "استرجع الجلسة السابقة" selector may prefer live continuity.
        prefer_live_dialogue = (
            selected_session.get("kind") == "latest"
            and live_dialogue_archive
            and "استرجع الجلسة السابقة" in normalized_session_request
            and not any(marker in normalized_session_request for marker in (
                "ملخص", "تقرير", "سياق", "حالة",
            ))
        )
        # "هذه الجلسة" / "الحوار الحالي" refers to the live DialogueMemory,
        # not to the latest persisted checkpoint. A reference-only selector is
        # deliberately not a saved-session selection and must not reach the
        # orchestrator's load_session() fallback.
        live_topic_summary = (
            selected_session.get("kind") == "none"
            and live_dialogue_archive
            and selected_session.get("output_kind") in {"brief", "topic_summary", "report"}
            and bool(str(selected_session.get("topic_filter") or "").strip())
        )
        explicit_live_branch_return = bool(
            self._resolve_generic_topic_reference(user_input)
            or self._ordinal_dialogue_exchange(user_input)
            or str((candidate.get("conversation_act") or "")).upper()
                in {"CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY", "TOPIC_RETURN"}
            or any(marker in self._normalize_transition_text(user_input) for marker in (
                "اكمل", "أكمل", "تابع", "واصل", "نكمل", "استمر",
            ))
            or str((candidate.get("response_attributes") or {}).get("dialogue_recovery", "")).casefold()
                in {"named_topic_return", "ordinal_topic_return", "interrupted_branch"}
        )
        if (
            not semantic_interrupted_recovery
            and not explicit_live_branch_return
            and (
                selected_session.get("kind") == "reference"
                or live_topic_summary
            )
            and selected_session.get("output_kind") in {
                "brief", "summary", "topic_summary", "report",
            }
        ):
            live_output_kind = str(selected_session.get("output_kind") or "summary")
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.MEMORY_DUMP,
                "target": "",
                "context": "general",
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_HISTORY_QUERY",
                "output_kind": live_output_kind,
                "response_attributes": {
                    "dialogue_response_mode": live_output_kind,
                },
                "source": "live_dialogue_reference",
            })
            raw_signal = dict(raw_signal or {})
            raw_signal.update({
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_HISTORY_QUERY",
                "response_attributes": {
                    "dialogue_response_mode": live_output_kind,
                },
                "conversational": True,
            })

        # Explicit saved-session language has precedence over the generic
        # dialogue-history act. Otherwise phrases such as "what were we saying
        # in the previous session?" are answered from the live dialogue and the
        # persisted-session selector never reaches the orchestrator. The selector
        # is deliberately phrase-based and returns "none" for ordinary history
        # questions, so those remain in the dialogue-memory path.
        if (
            selected_session.get("kind") not in {"none", "reference"}
            and not prefer_live_dialogue
            and not _restore_context
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.SESSION_RESTORE,
                "target": "",
                "context": "system",
                "session_selector": selected_session,
                "output_kind": selected_session.get("output_kind", "report"),
                "conversation_domain": "system",
                "conversation_act": "ASSISTANT_STATE_QUERY",
                "source": "session_selector",
            })
        saved_session_request = (
            selected_session.get("kind") not in {"none", "reference"}
            and not prefer_live_dialogue
            and not _restore_context
        )
        if prefer_live_dialogue:
            # This phrase is intentionally ambiguous between the most recent
            # live dialogue and a persisted session. When live exchanges exist,
            # the selector must not retain a saved-session identity downstream.
            selected_session = {
                **selected_session,
                "kind": "reference",
                "session_id": None,
                "number": None,
            }
            candidate = dict(candidate or {})
            candidate.pop("session_selector", None)
            candidate.update({
                "intent": Intent.MEMORY_DUMP,
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_HISTORY_QUERY",
                "output_kind": selected_session.get("output_kind") or "summary",
                "response_attributes": {"dialogue_response_mode": selected_session.get("output_kind") or "summary"},
                "source": "live_dialogue_reference",
            })
        if (
            selected_session.get("kind") == "none"
            and raw_signal.get("conversation_act") == "SAVED_SESSION_RESTORE_REQUEST"
        ):
            pending = getattr(self, "_pending_work_sessions", None)
            if pending is None:
                pending = getattr(
                    getattr(self.orchestrator, "agent", None),
                    "_pending_work_sessions",
                    [],
                ) or []
            choices = "، ".join(
                f"{item.get('number')} ({str((item.get('report') or {}).get('topic') or 'جلسة بلا عنوان')[:45]})"
                for item in pending
                if item.get("number") is not None
            )
            detail = (
                f"الجلسات المتاحة: {choices}."
                if choices
                else "لا توجد جلسات عمل محفوظة قابلة للاختيار حاليًا."
            )
            return self._finalize_direct_result({
                "status": "needs_clarification",
                "intent": Intent.SESSION_RESTORE,
                "source": "session_selector",
                "text": "اذكر رقم الجلسة التي تريد استرجاعها. " + detail,
                "executed": False,
                "semantic_request": {
                    "conversation_act": "SAVED_SESSION_RESTORE_REQUEST",
                    "response_attributes": {"saved_session_request": True},
                },
            }, intent=Intent.SESSION_RESTORE, route="L-SESSION",
               selected_session={"kind": "collection"}, saved_session_request=True)
        # A structurally enumerated multi-part message is one compound dialogue
        # request, not an agent-self/capability query merely because its framing
        # mentions testing the assistant. Preserve the whole request for one answer.
        compound_request = self._is_compound_multi_part_request(user_input)
        if compound_request:
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "UNKNOWN",
                "conversation_domain": "general",
                "conversation_act": "NONE",
                "response_attributes": {"compound_request": True},
                "semantic_pattern": "COMPOUND_DIALOGUE_REQUEST",
                "source": "compound_dialogue_request",
            })
            raw_signal = {
                "conversation_domain": "general",
                "conversation_act": "NONE",
                "confidence": 0.95,
                "response_attributes": {"compound_request": True},
                "conversational": True,
            }

        # A contextual acknowledgement such as "نعم أعرف" is not a new
        # executable request. Interpret it as continuation only when the latest
        # same-session assistant turn was itself asking a dialogue question.
        # This keeps the phrase context-sensitive instead of making it a global
        # continuation keyword.
        normalized_ack = self._normalize_transition_text(user_input).strip(
            " .,،؛:!?؟"
        )
        if (
            normalized_ack in {
                "نعم اعرف", "اي اعرف", "اعرف", "نعم اعلم", "اي اعلم",
                "نعم", "اجل", "اي", "ايه", "نعم اكمل", "اجل اكمل",
            }
            and self.dialogue_memory
        ):
            state = getattr(self.dialogue_memory, "state", None)
            session_id = str(getattr(state, "session_id", "") or "")
            recent_assistant = next(
                (
                    turn for turn in reversed(getattr(state, "history", []) or [])
                    if isinstance(turn, dict)
                    and turn.get("role") == "assistant"
                    and (
                        not session_id
                        or str(turn.get("session_id") or "") == session_id
                    )
                    and str(turn.get("context_kind") or "").casefold()
                    not in {"work", "system", "execution"}
                ),
                None,
            )
            prior_question = str(
                (recent_assistant or {}).get("content") or ""
            ).casefold()
            is_dialogue_question = bool(recent_assistant) and any(
                marker in prior_question
                for marker in (
                    "؟", "?", "هل", "تقصد", "اختر", "ما رأيك",
                    "شنو رأيك", "أي موضوع", "اي موضوع",
                )
            )
            if is_dialogue_question:
                raw_signal = dict(raw_signal or {})
                raw_signal.update({
                    "conversation_domain": "general",
                    "conversation_act": "CONVERSATION_CONTINUATION",
                    "confidence": 0.90,
                    "response_attributes": {},
                    "conversational": True,
                })
                candidate = dict(candidate or {})
                candidate.update({
                    "intent": Intent.PERSONAL_CHAT,
                    "target": "",
                    "entity_type": "REFERENCE",
                    "conversation_domain": "general",
                    "conversation_act": "CONVERSATION_CONTINUATION",
                    "conversation_confidence": 0.90,
                    "response_attributes": {},
                    "semantic_pattern": "CONTEXTUAL_DIALOGUE_ACKNOWLEDGEMENT",
                    "source": "contextual_dialogue_acknowledgement",
                })

        explicit_explanation = self._explicit_explanation_topic(user_input)
        explicit_topic = self._explicit_dialogue_topic(user_input)
        normalized_explanation_subject = self._normalize_transition_text(
            explicit_explanation or ""
        )
        cyber_explanation_markers = (
            "sql injection", "csrf", "cross site request forgery", "xss",
            "cross site scripting", "ssrf", "xxe", "idor", "rce",
            "command injection", "path traversal", "directory traversal",
            "phishing", "malware", "ransomware", "session hijacking",
            "clickjacking", "sql",
        )
        explicit_technical_explanation = bool(
            explicit_explanation
            and any(marker in normalized_explanation_subject for marker in cyber_explanation_markers)
        )
        if explicit_topic and not explicit_technical_explanation:
            # A named topic opener is social only when it is not already an
            # explicit technical explanation request.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": explicit_topic,
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "SOCIAL_OPENING",
                "conversation_confidence": 0.95,
                "semantic_pattern": "EXPLICIT_DIALOGUE_TOPIC",
                "source": "explicit_dialogue_topic",
            })
        normalized_social_text = str(user_input or "").casefold()
        explicit_casual_opening = any(marker in normalized_social_text for marker in (
            "بغيت نهضر معاك", "بغيت نهضر", "موضوع خفيف", "كيفاش داز نهارك",
            "كيف داز نهارك", "كيف كان نهارك", "كيف قضيت يومك", "خلينا نهضرو",
            "نهدرو شوية", "نهضر معاك شوية", "حوار ودي", "حوار عادي",
            "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
            "نريد أن نتحدث فقط", "نريد ان نتحدث فقط", "دردشة فقط",
        ))
        if explicit_casual_opening and not explicit_explanation:
            # An explicit casual opener is independent of a previously active
            # technical branch; do not inherit its target or prompt history.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": "social",
                "conversation_act": "CASUAL_CONVERSATION",
                "conversation_confidence": 0.98,
                "response_attributes": {},
                "semantic_pattern": "EXPLICIT_CASUAL_OPENING",
                "source": "explicit_casual_opening",
            })
        if explicit_explanation:
            # An explicit explain request is a fresh answer request, not an
            # implicit continuation merely because the sentence contains
            # "نقطة" or persisted dialogue state names the same topic.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.CYBER_EXPLAIN,
                "target": explicit_explanation,
                "entity_type": "CONCEPT",
                "conversation_domain": "technical",
                "conversation_act": (
                    raw_signal.get("conversation_act")
                    if is_style_act(raw_signal.get("conversation_act"))
                    else "NONE"
                ),
                "conversation_confidence": (
                    raw_signal.get("confidence", 0.0)
                    if is_style_act(raw_signal.get("conversation_act"))
                    else 0.95
                ),
                "response_attributes": (
                    dict(raw_signal.get("response_attributes") or {})
                    if is_style_act(raw_signal.get("conversation_act"))
                    else {}
                ),
                "semantic_pattern": "EXPLICIT_EXPLANATION_START",
                "source": "explicit_explanation_start",
            })
        # A correction such as "لا، قلت موضوع الكتب" names the branch to
        # restore. It must not fall through to a generic current-dialogue
        # summary, which can otherwise point at a greeting or the last reply.
        normalized_correction = self._normalize_transition_text(user_input)
        named_return = re.search(
            r"(?:قلت|اقصد|المقصود)\s+(?:موضوع\s+)?(الكتب|كتب|الفن|الرسم|النحت)",
            normalized_correction,
        )
        if named_return and any(marker in normalized_correction for marker in (
            "لا", "قلت", "اقصد", "المقصود", "كنا نناقش", "كنا نتحدث",
        )):
            named_topic = named_return.group(1)
            if named_topic == "كتب":
                named_topic = "الكتب"
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": named_topic,
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "named_topic_return"},
                "semantic_pattern": "NAMED_DIALOGUE_TOPIC_RETURN",
                "source": "named_dialogue_topic_return",
            })
        raw_act = raw_signal.get("conversation_act")
        if raw_act == "CORRECTION" and not named_return:
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": "general",
                "conversation_act": "CORRECTION",
                "conversation_confidence": raw_signal.get("confidence", 0.0),
                "response_attributes": dict(raw_signal.get("response_attributes") or {}),
                "semantic_pattern": "DIALOGUE_CORRECTION_OVERRIDE",
                "source": "dialogue_correction_override",
            })
        interrupted_recovery = str(
            (raw_signal.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold() == "interrupted_branch"
        if raw_act in {
            "CONVERSATION_HISTORY_QUERY",
            "CONVERSATION_CONTINUATION",
            "TOPIC_RETURN",
        } and not explicit_explanation and (
            not explicit_casual_opening
            or raw_act == "CONVERSATION_CONTINUATION"
        ) and not named_return and not self._is_explicit_targeted_proposal(user_input):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": raw_signal.get("conversation_domain", "general"),
                "conversation_act": raw_act,
                "conversation_confidence": raw_signal.get("confidence", 0.0),
                "response_attributes": dict(raw_signal.get("response_attributes") or {}),
                "semantic_pattern": "DIALOGUE_SEMANTIC_OVERRIDE",
                "source": "dialogue_semantic_override",
            })
            if (
                raw_act == "CONVERSATION_CONTINUATION"
                and self.dialogue_memory
                and not (
                    (raw_signal.get("response_attributes") or {}).get("dialogue_recovery")
                    == "interrupted_branch"
                )
            ):
                get_active_context = getattr(
                    self.dialogue_memory, "active_context_entity", None
                )
                active_context = (
                    get_active_context() if callable(get_active_context) else None
                )
                if isinstance(active_context, dict) and active_context.get("entity"):
                    active_action = str(active_context.get("action") or "").casefold()
                    active_type = str(active_context.get("entity_type") or "CONCEPT").upper()
                    technical_continuation = (
                        raw_signal.get("conversation_domain") in {"technical", "project"}
                        or active_action in {"cyber_explain", "explain"}
                        or active_type in {"FILE", "COMPONENT", "PROJECT"}
                    )
                    candidate.update({
                        "intent": (
                            Intent.CYBER_EXPLAIN
                            if technical_continuation
                            else Intent.PERSONAL_CHAT
                        ),
                        "target": active_context["entity"],
                        "entity_type": active_type,
                        "conversation_domain": (
                            "technical"
                            if technical_continuation
                            else raw_signal.get("conversation_domain", "general")
                        ),
                    })
                elif raw_act == "CONVERSATION_CONTINUATION":
                    # Social turns can intentionally clear active_context. For
                    # a bare "اكمل", recover only the latest explicitly named
                    # dialogue topic; never invent a topic from free-form text.
                    archive = getattr(
                        getattr(self.dialogue_memory, "state", None),
                        "exchange_archive",
                        [],
                    ) or []
                    archived_topic = next(
                        (
                            item for item in reversed(archive)
                            if isinstance(item, dict)
                            and str(item.get("target") or "").strip()
                            and item.get("context_kind") not in {"work", "system", "execution"}
                        ),
                        None,
                    )
                    if archived_topic:
                        candidate.update({
                            "target": str(archived_topic.get("target") or "").strip(),
                            "entity_type": "CONCEPT",
                            "conversation_domain": "general",
                        })
        # Preserve an explicitly named creative branch even when the sentence
        # is phrased as a negated correction ("لا أريد أن نعود إلى...").
        # Without this extraction the semantic layer sees only CONTINUATION
        # and the active branch remains the unrelated social conversation.
        normalized_topic_request = self._normalize_transition_text(user_input)
        if (
            raw_act == "CONVERSATION_CONTINUATION"
            and any(marker in normalized_topic_request for marker in ("فن", "رسم", "نحت", "نقش"))
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "الفن والرسم والنحت والنقش",
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "named_topic_return"},
                "semantic_pattern": "NAMED_DIALOGUE_TOPIC_RETURN",
                "source": "named_dialogue_topic_return",
            })
        ordinal_exchange = self._ordinal_dialogue_exchange(user_input)
        ordinal_exchange_target = str(
            (ordinal_exchange or {}).get("target")
            or (ordinal_exchange or {}).get("user")
            or ""
        ).strip()
        if ordinal_exchange and ordinal_exchange_target:
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": ordinal_exchange_target,
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "ordinal_topic_return"},
                "semantic_pattern": "ORDINAL_DIALOGUE_TOPIC_RETURN",
                "source": "ordinal_dialogue_topic_return",
            })
            # An ordinal exchange reference is an explicit branch restore,
            # not a generic continuation from the latest active topic.
            transition = ContextTransition.RESTORE
            if not active_report_followup:
                # The ordinal reference resolves against the live exchange
                # archive. Do not let a broad session selector redirect it
                # to a saved session or the work checkpoint.
                selected_session = {"kind": "reference"}
                selected_saved_session_id = None
                saved_session_request = False
                candidate.pop("session_selector", None)
        generic_social_topic_return = False
        normalized_return_request = self._normalize_transition_text(user_input)
        explicit_branch_return_request = any(marker in normalized_return_request for marker in (
            "ارجع", "نرجع", "عد الى", "عد إلى", "العودة الى", "العودة إلى",
            "رجوع الى", "رجوع إلى", "return to ", "back to ",
        ))
        explicit_topic_return = any(marker in normalized_return_request for marker in (
            "ارجع الى الموضوع", "ارجع لموضوع", "نرجع الى الموضوع",
            "نرجع لموضوع", "عد الى الموضوع", "عد لموضوع",
            "previous topic", "return to the topic", "back to the topic",
        ))
        generic_topic = (
            None
            if (
                _restore_context
                or named_return
                or (
                    raw_act == "CONVERSATION_HISTORY_QUERY"
                    and not explicit_topic_return
                )
            )
            or explicit_casual_opening
            or (interrupted_recovery and not explicit_topic_return)
            else self._resolve_generic_topic_reference(user_input)
        )
        if generic_topic:
            candidate = dict(candidate or {})
            is_ordinal_return = any(marker in str(user_input or "").casefold() for marker in (
                "الأول", "الاول", "الثاني", "الثانى", "first", "second",
                "ارجع", "عد إلى", "عد الى", "نرجع",
            ))
            state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
            archive = getattr(state, "exchange_archive", []) if state is not None else []
            normalized_topic = self._normalize_transition_text(generic_topic)
            restored_exchange = next(
                (
                    item for item in reversed(archive or [])
                    if isinstance(item, dict)
                    and not item.get("recall_only")
                    and (
                        self._normalize_transition_text(item.get("target") or "") == normalized_topic
                        or self._normalize_transition_text(item.get("user") or "") == normalized_topic
                    )
                    and str(item.get("context_transition") or "").casefold()
                        not in {"restore", "resume", "topic_return"}
                ),
                None,
            )
            restored_domain = str(
                (restored_exchange or {}).get("conversation_domain") or "general"
            ).casefold()
            restored_kind = str(
                (restored_exchange or {}).get("context_kind") or "dialogue"
            ).casefold()
            restored_intent = str(
                (restored_exchange or {}).get("intent") or ""
            ).casefold()
            restored_social_intent = restored_intent in {
                "personal_chat", "chat", "discussion", "question", "unclear",
            }
            restored_technical_intent = restored_intent in {
                "cyber_explain", "architecture", "propose_solution", "plan", "lab_plan",
            }
            restored_user_text = self._normalize_transition_text(
                (restored_exchange or {}).get("user") or ""
            )
            restored_social_topic = any(marker in restored_user_text for marker in (
                "موضوع عام", "نقاش عام", "حديث عام", "حوار عام",
                "دعنا نتحدث", "لنتحدث", "نتحدث عن",
            ))
            restored_social = bool(restored_exchange) and (
                restored_social_topic or (
                    restored_kind in {"dialogue", "social", "unknown"}
                    and restored_domain not in {
                        "technical", "project", "work", "system", "execution",
                    }
                    and (
                        restored_social_intent
                        or not restored_technical_intent
                    )
                )
            )
            history_reference = (
                raw_act == "CONVERSATION_HISTORY_QUERY"
                and bool((candidate.get("response_attributes") or {}).get("dialogue_response_mode"))
            )
            generic_social_topic_return = bool(restored_social)
            candidate.update({
                "intent": (
                    Intent.PERSONAL_CHAT
                    if restored_social or history_reference
                    else (
                        restored_intent
                        if restored_intent and restored_intent not in {
                            "personal_chat", "chat", "discussion", "question", "unclear",
                        }
                        else Intent.CYBER_EXPLAIN
                    )
                ),
                "target": generic_topic,
                "entity_type": "REFERENCE" if restored_social else "CONCEPT",
                "semantic_pattern": "GENERIC_TOPIC_REFERENCE",
                "conversation_domain": "general" if history_reference or restored_social else (
                    "technical" if restored_domain == "general" else restored_domain
                ),
                "conversation_act": (
                    "TOPIC_RETURN" if is_ordinal_return or explicit_topic_return
                    else "COMPOUND_REFERENCE"
                ),
                "conversation_confidence": 0.95,
            })
            if explicit_topic_return:
                response_attributes = dict(candidate.get("response_attributes") or {})
                response_attributes.pop("dialogue_recovery", None)
                candidate["response_attributes"] = response_attributes
        # A short additive follow-up belongs to the immediately preceding
        # dialogue exchange, not to a fresh social topic. Apply this only when
        # the latest archived exchange is dialogue-safe; never borrow work,
        # system, or execution context.
        normalized_follow_up = self._normalize_transition_text(user_input).strip(
            " .,،؛:!?؟"
        )
        # Arabic diacritics (e.g. tanween in "أيضًا") are orthographic,
        # not semantic; remove them for exact short-follow-up matching.
        normalized_follow_up = "".join(
            char for char in normalized_follow_up
            if not "\u064b" <= char <= "\u065f"
            and char != "\u0670"
            and not "\u06d6" <= char <= "\u06ed"
        )
        additive_follow_ups = {
            "ماذا ايضا", "ما ايضا", "وايضا", "وايش ايضا",
            "وماذا ايضا", "وماذا بعد", "ماذا بعد", "ما بعد",
            "شيء اخر", "شيئا اخر", "شي اخر", "شيئا اضافيا",
            "anything else", "what else", "and what else", "more",
        }
        if normalized_follow_up in additive_follow_ups and self.dialogue_memory:
            archived = getattr(
                getattr(self.dialogue_memory, "state", None),
                "exchange_archive",
                [],
            ) or []
            previous_exchange = next(
                (
                    item for item in reversed(archived)
                    if isinstance(item, dict)
                    and str(item.get("assistant") or "").strip()
                ),
                None,
            )
            previous_kind = str(
                (previous_exchange or {}).get("context_kind") or ""
            ).casefold()
            previous_domain = str(
                (previous_exchange or {}).get("conversation_domain") or ""
            ).casefold()
            if (
                previous_exchange
                and previous_kind in {"dialogue", "social"}
                and previous_domain not in {"work", "system", "execution"}
                and not self._is_explicit_targeted_proposal(user_input)
            ):
                candidate = dict(candidate or {})
                candidate.update({
                    "intent": Intent.PERSONAL_CHAT,
                    "target": "",
                    "entity_type": "REFERENCE",
                    "conversation_domain": "general",
                    "conversation_act": "CONVERSATION_CONTINUATION",
                    "conversation_confidence": 0.90,
                    "response_attributes": {},
                    "semantic_pattern": "CONTEXTUAL_ADDITIVE_FOLLOW_UP",
                    "source": "contextual_additive_follow_up",
                })

        # A bare topical elaboration inside an active social/dialogue branch
        # is part of that conversation, even when the fallback intent parser
        # labels the noun phrase as technical/executable. If it is allowed to
        # fall through with that domain, DialogueMemory.update rejects it and
        # the ordinal archive later has no exchange to restore.
        active_dialogue = (
            self.dialogue_memory.active_dialogue_branch()
            if self.dialogue_memory
            and callable(getattr(self.dialogue_memory, "active_dialogue_branch", None))
            else None
        )
        active_dialogue_domain = str(
            (active_dialogue or {}).get("conversation_domain") or "general"
        ).casefold()
        normalized_bare_topic = self._normalize_transition_text(user_input).strip(
            " .,،؛:!?؟"
        )
        has_dialogue_action = any(marker in normalized_bare_topic for marker in (
            "اشرح", "وضح", "فسر", "حلل", "نفذ", "شغل", "تشغيل", "انفذ",
            "اعطني", "اعطيني", "اقترح", "خطط", "كيف", "لماذا", "ما هو",
            "ماهي", "ما هي", "هل", "اريد", "أريد", "نريد", "اكتب",
            "ابن", "صمم", "راجع", "افحص", "اختبر",
        ))
        if (
            active_dialogue
            and active_dialogue_domain not in {
                "technical", "project", "work", "system", "execution",
            }
            and normalized_bare_topic
            and not has_dialogue_action
            and not is_style_act(candidate.get("conversation_act"))
            and not any(marker in normalized_bare_topic for marker in (
                "اكمل", "أكمل", "تابع", "واصل", "استمر", "نكمل",
                "اختصر", "بسط", "وضح", "فسر", "اشرح اكثر", "اشرح أكثر",
            ))
            and not self._is_explicit_topic_switch(user_input)
            and not explicit_branch_return_request
            and not named_return
            and not self._is_explicit_targeted_proposal(user_input)
            and not any(mark in str(user_input or "") for mark in ("؟", "?"))
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": str(user_input or "").strip(),
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "response_attributes": {},
                "semantic_pattern": "SOCIAL_DIALOGUE_TOPIC_ELABORATION",
                "source": "active_dialogue_topic_elaboration",
            })
            transition = ContextTransition.CONTINUE
        else:
            transition = self._classify_context_transition(mode, candidate, text=user_input)
        if ordinal_exchange and ordinal_exchange_target:
            # The ordinal resolver has already selected an exact archived
            # exchange and promoted its target into the candidate. Preserve
            # that explicit RESTORE decision after generic semantic
            # classification; otherwise the classifier sees only the
            # continuation wording and silently replaces it with CONTINUE.
            transition = ContextTransition.RESTORE
        if named_return:
            # A named correction is an explicit branch selection. Keep its
            # canonical topic and RESTORE transition authoritative over
            # generic correction/continuation classification.
            transition = ContextTransition.RESTORE
        interrupted_anchor = ""
        if interrupted_recovery and not generic_topic:
            # The wording describes a past topic switch, not a new switch now.
            # Restore the archived side branch when its subject is known;
            # otherwise keep the recovery request conversational and use the
            # bounded branch-selection fallback below.
            previous_context = (
                self.dialogue_memory.previous_context_entity()
                if self.dialogue_memory
                and callable(getattr(self.dialogue_memory, "previous_context_entity", None))
                else None
            )
            branch_exchanges = (
                self.dialogue_memory.interrupted_branch_exchanges()
                if self.dialogue_memory
                and callable(getattr(self.dialogue_memory, "interrupted_branch_exchanges", None))
                else []
            )
            if branch_exchanges:
                anchor_item = next(
                    (
                        item for item in branch_exchanges
                        if str(item.get("target") or item.get("user") or "").strip()
                    ),
                    {},
                )
                interrupted_anchor = " ".join(
                    part for part in (
                        str(anchor_item.get("target") or "").strip(),
                        str(anchor_item.get("user") or "").strip(),
                        str(anchor_item.get("assistant") or "").strip(),
                    ) if part
                )
                # Archive-only recovery must work even when the short visible
                # turn window or context_history no longer contains the branch.
                archived_target = next(
                    (
                        str(item.get("target") or "").strip()
                        for item in reversed(branch_exchanges)
                        if str(item.get("target") or "").strip()
                    ),
                    "",
                )
                if archived_target:
                    get_context = getattr(self.dialogue_memory, "context_for_topic", None)
                    archived_context = get_context(archived_target) if callable(get_context) else None
                    if not isinstance(archived_context, dict):
                        archived_exchange = next(
                            (
                                item for item in reversed(branch_exchanges)
                                if str(item.get("target") or "").strip() == archived_target
                            ),
                            {},
                        )
                        archived_context = {
                            "entity": archived_target,
                            "action": str(archived_exchange.get("intent") or "cyber_explain"),
                            "entity_type": (
                                "CONCEPT"
                                if str(archived_exchange.get("conversation_domain") or "").casefold() == "technical"
                                else "UNKNOWN"
                            ),
                        }
                    previous_context = archived_context
                    candidate = dict(candidate or {})
                    candidate["target"] = archived_target
                    restored_entity_type = str(
                        archived_context.get("entity_type") or "CONCEPT"
                    ).upper()
                    restored_action = str(
                        archived_context.get("action") or ""
                    ).casefold()
                    candidate["entity_type"] = restored_entity_type

                    # The semantic override initially labels a generic return
                    # as personal_chat. Once interrupted-branch recovery has
                    # resolved a concrete archived branch, restore that
                    # branch's canonical action instead of dispatching the
                    # recovery utterance as chat.
                    if restored_action not in {
                        "", "personal_chat", "chat", "discussion",
                        "question", "unclear",
                    }:
                        candidate["intent"] = archived_context["action"]
                    elif (
                        restored_entity_type in {"CONCEPT", "COMPONENT", "FILE", "PROJECT"}
                        and str(
                            archived_context.get("conversation_domain") or
                            ("technical" if restored_entity_type == "CONCEPT" else "")
                        ).casefold() in {"technical", "project"}
                    ):
                        candidate["intent"] = Intent.CYBER_EXPLAIN

                    if restored_entity_type in {"CONCEPT", "COMPONENT"}:
                        candidate["conversation_domain"] = "technical"
            transition = (
                ContextTransition.RESTORE
                if branch_exchanges or (
                    isinstance(previous_context, dict) and previous_context.get("entity")
                )
                else ContextTransition.AMBIGUOUS
            )
        if (
            explicit_casual_opening
            and not explicit_explanation
            and raw_act != "CONVERSATION_CONTINUATION"
        ):
            # Social openings are independent turns: never attach the previous
            # technical entity or its prompt history to the semantic request.
            transition = ContextTransition.NEW_INDEPENDENT
        # An explicit independent-topic marker overrides a parser-produced
        # compound/reference act. The old branch must not enter a new topic's
        # prompt or trigger privacy blocking because of stale content.
        if not interrupted_recovery and (
            self._is_explicit_independent_topic(user_input, candidate)
            or self._is_explicit_topic_switch(user_input)
        ):
            # Independent-topic intent and explicit topic-switch wording are
            # separate signals. An active branch alone must not turn every
            # independent request into EXPLICIT_SWITCH.
            transition = (
                ContextTransition.EXPLICIT_SWITCH
                if self._is_explicit_topic_switch(user_input)
                else ContextTransition.NEW_INDEPENDENT
            )
            # The legacy context resolver may have already inherited the old
            # target before the transition marker was evaluated. Recover the
            # explicit subject after an explanation or dialogue-switch phrase.
            import re as _re
            independent_subject = _re.search(
                r"(?:اشرح|عن|حول|explain|ننتقل|انتقل)\s+(?:(?:الى|إلى)\s+|ل)?([^،,.؟?]+)",
                user_input,
                flags=_re.IGNORECASE,
            )
            if independent_subject:
                subject = independent_subject.group(1).strip()
                subject = _re.split(
                    r"\s+(?=بالتفصيل|باختصار|ثم(?:\s|$)|و(?:\s|$))",
                    subject,
                    maxsplit=1,
                )[0]
                if subject:
                    candidate = dict(candidate or {})
                    candidate["target"] = subject
                    technical_independent_explanation = bool(explicit_explanation)
                    candidate["intent"] = (
                        Intent.CYBER_EXPLAIN
                        if technical_independent_explanation
                        else (Intent.PERSONAL_CHAT if explicit_topic else Intent.CYBER_EXPLAIN)
                    )
                    candidate["entity_type"] = "CONCEPT"
                    candidate["conversation_domain"] = (
                        "technical"
                        if technical_independent_explanation
                        else ("general" if explicit_topic else "technical")
                    )
                    if technical_independent_explanation:
                        candidate["conversation_act"] = "EXECUTABLE_REQUEST"
            else:
                # Do not carry an inherited target into a new subjectless topic.
                candidate = dict(candidate or {})
                candidate["target"] = ""
                candidate["entity_type"] = "UNKNOWN"
                if not explicit_explanation:
                    candidate["intent"] = Intent.PERSONAL_CHAT
                    candidate["conversation_domain"] = "social"
        if (
            selected_session.get("kind") not in {"none", "reference"}
            and not prefer_live_dialogue
            and not _restore_context
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.SESSION_RESTORE,
                "target": "",
                "context": "system",
                "session_selector": selected_session,
                "conversation_domain": "system",
                "conversation_act": "ASSISTANT_STATE_QUERY",
                "source": "session_selector",
            })
        # Reassert compound-test ownership after every legacy override above;
        # an incidental friendly phrase or session keyword inside one numbered
        # item must not steal the whole message's route.
        if compound_request:
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "UNKNOWN",
                "conversation_domain": "general",
                "conversation_act": "NONE",
                "response_attributes": {"compound_request": True},
                "semantic_pattern": "COMPOUND_DIALOGUE_REQUEST",
                "source": "compound_dialogue_request",
            })
            transition = ContextTransition.NEW_INDEPENDENT

        self._clear_unrelated_execution_file(transition, candidate)
        resolved_input = (
            f"{interrupted_anchor} {user_input}".strip()
            if interrupted_recovery and interrupted_anchor
            else user_input
        )
        parsed = candidate
        normalized_assistant_reply_query = self._normalize_transition_text(user_input)
        direct_assistant_reply_lookup = bool(
            re.search(
                r"(?:اخر|الاخير|اول|الاول)\s+(?:رد|جواب|اجابه)",
                normalized_assistant_reply_query,
            )
            and re.search(
                r"(?:كتب|قلت|كان|ردك|الوكيل|انت)",
                normalized_assistant_reply_query,
            )
        )
        if direct_assistant_reply_lookup and not saved_session_request:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_HISTORY_QUERY",
                "response_attributes": {
                    **dict(parsed.get("response_attributes") or {}),
                    "dialogue_recall": True,
                },
                "semantic_pattern": "DIRECT_ASSISTANT_REPLY_RECALL",
                "source": "dialogue_memory",
            })

        dialogue_context_query = (
            any(marker in normalized_assistant_reply_query for marker in (
                "كلامي", "اقصد", "اعني", "سياق الحوار", "سياق الحديث",
                "رد غير مناسب", "لماذا ترد", "نناقشه", "نناقشها",
                "تكمل الحوار", "استكمال الحوار", "اخر نقطة", "اخر نقطه",
            ))
            and not direct_assistant_reply_lookup
            and not saved_session_request
            and not named_return
            and not interrupted_recovery
        )
        if dialogue_context_query:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "response_attributes": {
                    **dict(parsed.get("response_attributes") or {}),
                    "dialogue_context_reference": True,
                },
                "semantic_pattern": "ACTIVE_DIALOGUE_CONTEXT_REFERENCE",
                "source": "active_dialogue_context",
            })
            active_state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
            if getattr(active_state, "exchange_archive", None):
                transition = ContextTransition.CONTINUE

        normalized_memory_request = self._normalize_transition_text(user_input)
        dialogue_memory_search_request = bool(
            any(marker in normalized_memory_request for marker in (
                "ابحث", "بحث", "فتش", "دور",
            ))
            and any(marker in normalized_memory_request for marker in (
                "ذاكره", "ذاكرة", "الحوار", "المحادثه", "المحادثة", "النقاش",
            ))
            and not any(marker in normalized_memory_request for marker in (
                "جلسة", "جلسه", "الجلسات", "المحفوظة", "المحفوظ", "session",
                "ملف", "ملفات", "مشروع", "كود",
            ))
        )
        if dialogue_memory_search_request:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_HISTORY_QUERY",
                "output_kind": "summary",
                "response_attributes": {
                    **dict(parsed.get("response_attributes") or {}),
                    "dialogue_response_mode": "summary",
                    "dialogue_recall": True,
                },
                "semantic_pattern": "EXPLICIT_DIALOGUE_MEMORY_SEARCH",
                "source": "dialogue_memory",
            })
        explicit_saved_memory_scope = any(marker in normalized_memory_request for marker in (
            "جلسة", "جلسه", "الجلسات", "الجلسات المحفوظه",
            "الجلسة المحفوظة", "الجلسه المحفوظه", "session",
        ))
        if (
            str(parsed.get("conversation_act") or "").upper() == "CONVERSATION_HISTORY_QUERY"
            and any(marker in normalized_memory_request for marker in (
                "ابحث", "بحث", "فتش", "دور", "ذاكره", "ذاكرة",
            ))
            and not explicit_saved_memory_scope
        ):
            selected_session = {"kind": "none"}
            selected_saved_session_id = None
            saved_session_request = False
        context_entity = None
        if self.dialogue_memory:
            if transition == ContextTransition.RESTORE:
                get_context = getattr(
                    self.dialogue_memory,
                    "context_for_topic",
                    None,
                )
                if callable(get_context):
                    context_entity = get_context(candidate.get("target"))
                if context_entity is None and not generic_social_topic_return:
                    get_previous = getattr(
                        self.dialogue_memory,
                        "previous_context_entity",
                        None,
                    )
                    if callable(get_previous):
                        context_entity = get_previous()
            elif transition.value in CONTEXTUAL_TRANSITIONS:
                get_active_context = getattr(
                    self.dialogue_memory,
                    "active_context_entity",
                    None,
                )
                if callable(get_active_context):
                    context_entity = get_active_context()

        active_branch = context_entity
        get_branch = getattr(self.dialogue_memory, "active_dialogue_branch", None) if self.dialogue_memory else None
        if transition != ContextTransition.RESTORE and callable(get_branch):
            active_branch = get_branch() or context_entity
        branch_domain = str((active_branch or {}).get("conversation_domain") or "general").casefold()
        branch_action = str((active_branch or {}).get("action") or "").casefold()
        branch_is_dialogue = bool(active_branch) and (
            branch_domain not in {"technical", "project", "work", "system", "execution"}
            or branch_action in {"personal_chat", "chat", "discussion"}
        )
        normalized_active_followup = self._normalize_transition_text(user_input).strip()
        active_style_request = is_style_act(parsed.get("conversation_act"))
        active_short_followup = (
            normalized_active_followup in {
                "اكمل", "اكمل اكثر", "تابع", "واصل", "استمر",
                "نكمل", "وضح الفكرة", "بسط الشرح", "اشرح اكثر",
                "اشرح اكثر قليلا", "اشرح اكثر من ذلك",
            }
            or any(marker in normalized_active_followup for marker in (
                "جيد جدا اكمل", "اكمل الشرح", "تابع الشرح", "واصل الشرح",
                "نكمل الشرح", "وضح اكثر", "وضح أكثر",
            ))
        )
        if (
            branch_is_dialogue
            and active_branch.get("entity")
            and transition in CONTEXTUAL_TRANSITIONS
            and (active_style_request or active_short_followup)
        ):
            parsed = dict(parsed or {})
            parsed["target"] = active_branch["entity"]
            parsed["entity_type"] = active_branch.get("entity_type") or "CONCEPT"
            parsed["intent"] = Intent.PERSONAL_CHAT
            parsed["conversation_domain"] = "general"
            if not active_style_request:
                parsed["conversation_act"] = "CONVERSATION_CONTINUATION"
            transition = ContextTransition.CONTINUE

        parsed_intent_value = str(
            getattr(parsed.get("intent"), "value", parsed.get("intent")) or ""
        ).casefold()
        # A short ordinal question (e.g. "ما الاقتراح الأول؟") is a contextual
        # dialogue reference only when a dialogue branch is already active.
        # Do not let a targetless proposal parser turn it into a new operation.
        if (
            branch_is_dialogue
            and self._is_contextual_ordinal_follow_up(user_input)
            and not self._is_explicit_topic_switch(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "TOPIC_CONTINUATION_QUERY",
                "response_attributes": {},
                "semantic_pattern": "DIALOGUE_ORDINAL_FOLLOW_UP",
            })
            transition = ContextTransition.CONTINUE
            parsed_intent_value = "personal_chat"

        diagnostic_intents = {"health", "self_diagnose", "full_diagnose", "run_diagnostics"}
        if (
            branch_is_dialogue
            and not str(parsed.get("target") or "").strip()
            and str(parsed.get("conversation_act") or "").upper()
            in {"CASUAL_CONVERSATION", "GENERAL_CHAT", "SOCIAL_FOLLOW_UP"}
            and not self._is_explicit_topic_switch(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_SOCIAL_CONTINUATION_GUARD",
            })
            transition = ContextTransition.CONTINUE
        if (
            branch_is_dialogue
            and parsed_intent_value in diagnostic_intents
            and not self._is_explicit_diagnostic_request(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_DIAGNOSTIC_GUARD",
            })
            transition = ContextTransition.CONTINUE
            parsed_intent_value = "personal_chat"

        normalized_turn = self._normalize_transition_text(user_input)
        if (
            branch_is_dialogue
            and parsed_intent_value in {
                getattr(item, "value", item).casefold() for item in _AGENT_SELF_INTENTS
            }
            and "هل تستطيع" in normalized_turn
            and any(marker in normalized_turn for marker in ("تشخيص", "فحص", "تحليل"))
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_CAPABILITY_GUARD",
            })
            transition = ContextTransition.CONTINUE
            parsed_intent_value = "personal_chat"

        if (
            branch_is_dialogue
            and transition in {ContextTransition.CONTINUE, ContextTransition.REFERENCE}
            and parsed_intent_value in {"cyber_explain", "plan", "propose_solution", "lab_plan"}
            and not self._explicit_explanation_topic(user_input)
            and not self._is_explicit_topic_switch(user_input)
            and not self._is_explicit_targeted_proposal(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_CONTINUATION_GUARD",
            })
            parsed_intent_value = "personal_chat"

        normalized_reference = self._normalize_transition_text(user_input)
        if active_branch and normalized_reference in {
            "هذا", "هذه", "ذلك", "تلك", "ماذا يعني هذا", "ما معنى هذا",
            "اشرح لي هذا", "وضح هذا",
        }:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": branch_domain if branch_domain in {"social", "general"} else "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_REFERENCE_RESOLUTION",
            })
            transition = ContextTransition.CONTINUE

        style_request = is_style_act(candidate.get("conversation_act"))
        recovery_mode = str(
            (candidate.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        unnamed_branch_return = recovery_mode == "interrupted_branch"
        if (
            self.dialogue_memory
            and context_entity
            and not generic_social_topic_return
            and transition.value in CONTEXTUAL_TRANSITIONS
            and not style_request
            and not unnamed_branch_return
            and not self._is_explicit_targeted_proposal(user_input)
            and (
                not candidate.get("target")
                or str(candidate.get("entity_type", "")).upper()
                in {"REFERENCE", "ELABORATION"}
                or (
                    str(candidate.get("conversation_act") or "").upper()
                    in {"CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY"}
                    and str(context_entity.get("action") or "").casefold()
                    in {"cyber_explain", "explain"}
                )
                or recovery_mode == "ordinal_topic_return"
            )
        ):
            resolved_input = self.dialogue_memory.resolve_references(
                user_input,
                context_entity=context_entity,
            )
            # ELABORATION is an explicit contextual follow-up. If the resolver
            # leaves it unchanged, make the authorized reference explicit before
            # the second canonical parse (without doing this for ambiguous turns).
            if (
                resolved_input == user_input
                and str(parsed.get("entity_type") or "").upper() == "ELABORATION"
                and context_entity.get("entity")
            ):
                resolved_input = f"{context_entity['entity']} {user_input}".strip()
            context_action = str(context_entity.get("action") or "").casefold()
            social_active_context = (
                context_action not in {"cyber_explain", "explain"}
                and str(context_entity.get("entity_type") or "").upper()
                not in {"FILE", "COMPONENT", "PROJECT"}
            )
            if resolved_input != user_input and not social_active_context:
                parsed = self._safe_parse(
                    resolved_input,
                    context_entity=context_entity,
                )
            elif social_active_context and transition == ContextTransition.CONTINUE:
                # The active social branch owns this follow-up. Re-parsing a
                # synthetic string such as "الفن ... اكمل" lets legacy
                # explanation rules seize it as cyber_explain.
                parsed = dict(parsed or {})
                parsed["intent"] = Intent.PERSONAL_CHAT
                parsed["target"] = context_entity.get("entity")
                parsed["entity_type"] = context_entity.get("entity_type", "CONCEPT")
                parsed["conversation_domain"] = "general"
                parsed["conversation_act"] = "CONVERSATION_CONTINUATION"

        if (
            context_entity
            and transition.value in CONTEXTUAL_TRANSITIONS
            and not style_request
            and parsed.get("intent") in _NON_EXECUTABLE_INTENTS
            and str(context_entity.get("entity_type", "")).upper() in {"FILE", "COMPONENT", "PROJECT"}
        ):
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.CYBER_EXPLAIN
            parsed["target"] = context_entity.get("entity")
            parsed["entity_type"] = context_entity.get("entity_type")
            parsed["conversation_domain"] = "project"

        if (
            context_entity
            and transition == ContextTransition.CONTINUE
            and not style_request
            and str(context_entity.get("action") or "").casefold()
            in {"cyber_explain", "explain"}
            and parsed.get("intent") in _NON_EXECUTABLE_INTENTS
        ):
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.CYBER_EXPLAIN
            parsed["target"] = context_entity.get("entity")
            parsed["entity_type"] = context_entity.get("entity_type", "CONCEPT")
            parsed["conversation_domain"] = "technical"

        # Normalize generic reference words after, not before, the memory
        # owner has supplied the authorized subject. With no subject, erase
        # the parser's lexical placeholder so the executor cannot receive it
        # as a real target.
        normalized_target = self._normalize_transition_text(parsed.get("target"))
        if normalized_target in {
            "هذا", "هذه", "ذلك", "تلك", "هذا الامر", "ذلك الامر",
            "الامر", "الفكرة", "الموضوع", "الشرح", "النقطة",
        }:
            parsed = dict(parsed or {})
            if context_entity and context_entity.get("entity"):
                parsed["target"] = context_entity["entity"]
                parsed["entity_type"] = context_entity.get("entity_type", "REFERENCE")
            else:
                parsed["target"] = ""

        # The ordinal resolver selects an exact archived exchange before the
        # generic context guards run. Those guards may legitimately prefer the
        # active branch for ordinary follow-ups, but must not rewrite an
        # explicit ordinal return (e.g. "قبل ردين") into CONTINUE. Reassert
        # both the selected subject and RESTORE at the history boundary, where
        # the branch is actually materialized for the prompt.
        if ordinal_exchange and ordinal_exchange_target and not saved_session_request:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": ordinal_exchange_target,
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "ordinal_topic_return"},
                "semantic_pattern": "ORDINAL_DIALOGUE_TOPIC_RETURN",
                "source": "ordinal_dialogue_topic_return",
            })
            transition = ContextTransition.RESTORE

        # Explicit "do not change the topic" wording is a continuity
        # constraint. Resolve the active branch from its saved exchange, not
        # from a secondary noun (for example "SQL") inside the same sentence.
        normalized_same_topic = self._normalize_transition_text(user_input)
        same_topic_requested = any(marker in normalized_same_topic for marker in (
            "بدون تغيير الموضوع", "دون تغيير الموضوع", "لا تغير الموضوع",
            "لا نغير الموضوع", "نفس الموضوع", "without changing the topic",
            "keep the same topic",
        ))
        if same_topic_requested and not saved_session_request and self.dialogue_memory:
            active_archive = getattr(
                getattr(self.dialogue_memory, "state", None),
                "exchange_archive",
                [],
            ) or []
            active_exchange = next((
                item for item in reversed(active_archive)
                if isinstance(item, dict)
                and str(item.get("target") or "").strip()
                and not item.get("recall_only")
                and not item.get("state_boundary_only")
                and str(item.get("context_kind") or "dialogue").casefold()
                    not in {"work", "system", "execution"}
            ), None)
            if active_exchange:
                parsed = dict(parsed or {})
                parsed.update({
                    "intent": Intent.PERSONAL_CHAT,
                    "target": str(active_exchange.get("target") or "").strip(),
                    "entity_type": "CONCEPT",
                    "conversation_domain": str(
                        active_exchange.get("conversation_domain") or "general"
                    ).casefold(),
                    "conversation_act": "CONVERSATION_CONTINUATION",
                    "response_attributes": {"same_topic_constraint": True},
                    "semantic_pattern": "EXPLICIT_SAME_TOPIC_CONTINUATION",
                    "source": "active_dialogue_branch",
                })
                transition = ContextTransition.CONTINUE

        # An explicit internal restore request must retain RESTORE semantics
        # after parser enrichment; it must not degrade to ordinary CONTINUE.
        if _restore_context:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": str(_restore_context.get("entity") or "").strip(),
                "entity_type": _restore_context.get("entity_type", "CONCEPT"),
                "conversation_domain": str(
                    _restore_context.get("conversation_domain") or "general"
                ).casefold(),
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "named_topic_return"},
                "semantic_pattern": "AUTHORIZED_DIALOGUE_RESTORE",
                "source": "authorized_dialogue_restore",
            })
            transition = ContextTransition.RESTORE

        # A saved-session selector is an explicit routing decision. Context
        # enrichment above may re-parse a synthetic reference and discard
        # selector metadata, so reassert saved-session ownership immediately
        # before semantic construction and keep the request isolated from the
        # active dialogue branch.
        if saved_session_request:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.SESSION_RESTORE,
                "target": "",
                "context": "system",
                "session_selector": selected_session,
                "conversation_domain": "system",
                "conversation_act": "ASSISTANT_STATE_QUERY",
                "source": "session_selector",
            })
            transition = ContextTransition.NEW_INDEPENDENT
            context_entity = None
            chat_history = []
        else:
            chat_history = self._history_for_transition(transition, parsed)

        if interrupted_recovery and self.dialogue_memory:
            # Use the exact branch selected from the durable exchange archive.
            # Recent visible turns may still belong to the intervening branch.
            selected_recovery_branch = self.dialogue_memory.interrupted_branch_exchanges()
            chat_history = (
                self._exchange_history_turns(selected_recovery_branch[-4:])[-8:]
                if selected_recovery_branch else []
            )

        parsed = dict(parsed or {})
        conversation_act = str(parsed.get("conversation_act") or "NONE")
        if transition == ContextTransition.RESTORE:
            conversation_act = "TOPIC_RETURN"
        elif transition == ContextTransition.EXPLICIT_SWITCH:
            conversation_act = "TOPIC_SHIFT"
        elif (
            transition.value in CONTEXTUAL_TRANSITIONS
            and conversation_act == "NONE"
        ):
            conversation_act = "CONVERSATION_CONTINUATION"
        parsed["conversation_act"] = conversation_act
        parsed.setdefault("conversation_domain", "general")
        parsed.setdefault("conversation_confidence", 0.0)
        parsed.setdefault("response_attributes", {})

        # A bare explanation imperative is an incomplete technical request,
        # not a general knowledge question. Preserve Orchestrator ownership so
        # it can ask for the missing subject instead of answering speculatively.
        normalized_incomplete_explanation = self._normalize_transition_text(user_input)
        parsed_intent_value = str(
            getattr(parsed.get("intent"), "value", parsed.get("intent")) or ""
        ).casefold()
        if (
            parsed_intent_value == "cyber_explain"
            and not str(parsed.get("target") or "").strip()
            and normalized_incomplete_explanation in {
                "اشرح", "اشرح لي", "وضح", "وضح لي", "فسر", "فسر لي",
                "explain", "describe",
            }
        ):
            response_attributes = dict(parsed.get("response_attributes") or {})
            response_attributes["incomplete_explanation_request"] = True
            parsed["response_attributes"] = response_attributes

        # Generic targetless proposals are dialogue, even when the fallback parser
        # labels their domain as execution. Preserve execution ownership only when
        # the user actually asks to run/execute/deploy something or names a target.
        proposal_intent = str(
            getattr(parsed.get("intent"), "value", parsed.get("intent")) or ""
        ).casefold()
        proposal_domain = str(parsed.get("conversation_domain") or "general").casefold()
        proposal_target = str(parsed.get("target") or "").strip()
        normalized_proposal_text = self._normalize_transition_text(user_input)
        explicit_execution_markers = (
            "نفذ", "نفذ الامر", "ابدأ التنفيذ", "ابدا التنفيذ",
            "شغل", "تشغيل", "انشر", "تنفيذ", "execute", "run", "deploy",
        )
        if (
            proposal_intent in {"propose_solution", "plan"}
            and not proposal_target
            and proposal_domain == "execution"
            and not any(
                marker in normalized_proposal_text
                for marker in explicit_execution_markers
            )
        ):
            parsed["conversation_domain"] = "general"

        # Explicit targeted proposals are independent requests. Reassert this
        # ownership after legacy context/continuation overrides so the active
        # social branch cannot rewrite a concrete proposal as casual dialogue.
        if self._is_explicit_targeted_proposal(user_input):
            normalized_proposal = self._normalize_transition_text(user_input)
            target_match = re.search(
                r"(?:لمشكلة|بخصوص|حول|عن)\s+(.+)$",
                normalized_proposal,
            )
            proposal_target = (
                str((target_match.group(1) if target_match else "") or "").strip()
                or str((parsed or {}).get("target") or "").strip()
                or str(user_input or "").strip()
            )
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PROPOSE_SOLUTION,
                "target": proposal_target,
                "entity_type": "CONCEPT",
                "conversation_domain": "technical",
                "conversation_act": "NONE",
                "semantic_pattern": "EXPLICIT_TARGETED_PROPOSAL",
                "source": "explicit_targeted_proposal",
            })
            transition = ContextTransition.NEW_INDEPENDENT
            context_entity = None
            chat_history = []

        normalized_live_continuation = self._normalize_transition_text(user_input)
        live_continuation_request = any(marker in normalized_live_continuation for marker in (
            "نكمل في نفس سياق الموضوع", "نعم نكمل", "اجل نكمل",
            "نواصل في نفس السياق", "نكمل في نفس السياق",
        ))
        live_state_for_continuation = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        live_session_id_for_continuation = str(
            getattr(live_state_for_continuation, "session_id", "") or ""
        )
        has_dialogue_evidence_for_continuation = any(
            isinstance(item, dict)
            and (
                not live_session_id_for_continuation
                or str(item.get("session_id") or "") == live_session_id_for_continuation
            )
            and not item.get("recall_only")
            and not item.get("state_boundary_only")
            and str(item.get("context_kind") or "dialogue").casefold() not in {"work", "system", "execution"}
            and str(item.get("conversation_domain") or "general").casefold() not in {"work", "system", "execution"}
            and str(item.get("user") or "").strip()
            and str(item.get("assistant") or "").strip()
            for item in (getattr(live_state_for_continuation, "exchange_archive", []) or [])
        ) or (
            live_state_for_continuation is not None
            and any(
                isinstance(item, dict)
                and item.get("role") == "user"
                and (
                    not live_session_id_for_continuation
                    or str(item.get("session_id") or "") == live_session_id_for_continuation
                )
                and str(item.get("context_kind") or "dialogue").casefold() not in {"work", "system", "execution"}
                and str(item.get("conversation_domain") or "general").casefold() not in {"work", "system", "execution"}
                and str(item.get("content") or "").strip()
                for item in (getattr(live_state_for_continuation, "history", []) or [])
            )
            and any(
                isinstance(item, dict)
                and item.get("role") == "assistant"
                and (
                    not live_session_id_for_continuation
                    or str(item.get("session_id") or "") == live_session_id_for_continuation
                )
                and str(item.get("context_kind") or "dialogue").casefold() not in {"work", "system", "execution"}
                and str(item.get("conversation_domain") or "general").casefold() not in {"work", "system", "execution"}
                and str(item.get("content") or "").strip()
                for item in (getattr(live_state_for_continuation, "history", []) or [])
            )
        )
        if (
            live_continuation_request
            and has_dialogue_evidence_for_continuation
            and not saved_session_request
            and not active_report_followup
            and not any(marker in normalized_live_continuation for marker in (
                "العمل", "الملف", "المهمة", "مشروع", "work", "file", "task",
            ))
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "source": "live_dialogue_continuation",
            })
            transition = ContextTransition.CONTINUE
            chat_history = self._history_for_transition(transition, candidate)
            selected_session = {"kind": "reference"}
            selected_saved_session_id = None
            candidate.pop("session_selector", None)
            saved_session_request = False
        if (
            not saved_session_request
            and not explicit_live_branch_return
            and self._dialogue_recall_requested(user_input, parsed)
        ):
            parsed = dict(parsed or {})
            parsed["conversation_act"] = "CONVERSATION_HISTORY_QUERY"
            parsed["response_attributes"] = {
                **dict(parsed.get("response_attributes") or {}),
                "dialogue_recall": True,
            }
        normalized_suggestion_request = self._normalize_transition_text(user_input)
        if (
            str(getattr(parsed.get("intent"), "value", parsed.get("intent")) or "").casefold()
                == "propose_solution"
            and not str(parsed.get("target") or "").strip()
            and any(marker in normalized_suggestion_request for marker in (
                "انت اعطيني اقتراحات", "انت اعطني اقتراحات",
                "اقترح انت بعض المواضيع", "اقترح بعض المواضيع",
                "اقترح موضوع", "اقترح شي موضوع",
                "نت قتارح شي موضوع", "عن اي موضوع قتارح نتا",
                "اقترحات اخرى", "اقتراحات اخرى في مجال اخر",
                "اريد اقتراحات اخرى في مجال اخر",
            ))
        ):
            parsed = dict(parsed or {})
            attributes = dict(parsed.get("response_attributes") or {})
            attributes["local_social_suggestion"] = True
            parsed["response_attributes"] = attributes

        # Dialogue-feature engineering discussion is technical context, not
        # a social opener or a request to retrieve the dialogue archive.
        normalized_feature_discussion = self._normalize_transition_text(user_input)
        if any(marker in normalized_feature_discussion for marker in (
            "نطور سياق الحوار", "تطوير سياق الحوار", "تصحيح مسار الحوار",
            "طبقات الذاكرة", "استرجاع الحوار بشكل صحيح",
            "استرجاع الحوار داخل الوكيل", "استمرارية الحوار",
            "تحسين استرجاع الحوار",
        )):
            parsed = dict(parsed or {})
            parsed["conversation_domain"] = "technical"
            attributes = dict(parsed.get("response_attributes") or {})
            attributes["dialogue_feature_discussion"] = True
            parsed["response_attributes"] = attributes
        recovery_mode = str(
            (parsed.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        recovery_intent = parsed.get("intent")
        recovery_intent_is_dialogue = bool(
            recovery_intent in _NON_EXECUTABLE_INTENTS
            or recovery_intent == Intent.MEMORY_DUMP
        )
        recovery_is_dialogue = bool(
            recovery_mode in {"interrupted_branch", "named_topic_return", "ordinal_topic_return"}
            and (recovery_intent_is_dialogue or interrupted_recovery)
        )
        if recovery_intent_is_dialogue and recovery_mode in {"interrupted_branch", "named_topic_return"}:
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.PERSONAL_CHAT
            parsed["conversation_domain"] = "general"
            mode = "CHAT"
        elif recovery_mode and not recovery_is_dialogue:
            # A stale recovery annotation must never rewrite an explicit
            # executable/knowledge intent into a dialogue continuation.
            parsed = dict(parsed or {})
            attributes = dict(parsed.get("response_attributes") or {})
            attributes.pop("dialogue_recovery", None)
            parsed["response_attributes"] = attributes
            recovery_mode = ""
        local_project_answer = (
            self._local_project_progress_answer(user_input, parsed, context_entity)
            if not saved_session_request and not _restore_context else None
        )
        ambiguous_resume = self._ambiguous_resume_without_domain(user_input, parsed)

        normalized_history_question = self._normalize_transition_text(user_input)
        prior_message_topic_question = (
            "موضوع" in normalized_history_question
            and "كنا" in normalized_history_question
            and any(marker in normalized_history_question for marker in ("نشرح", "نشرحه", "شرح"))
            and any(marker in normalized_history_question for marker in ("رساله", "رسالت", "رسائل"))
            and any(marker in normalized_history_question for marker in ("سابق", "سابقه", "قبل"))
        )
        if prior_message_topic_question:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_HISTORY_QUERY",
                "output_kind": "summary",
                "response_attributes": {"dialogue_response_mode": "summary"},
                "semantic_pattern": "PRIOR_MESSAGE_TOPIC_RECALL",
                "source": "dialogue_memory",
            })
            transition = ContextTransition.CONTINUE
            recovery_is_dialogue = False
            # The topic phrase refers to earlier dialogue content, not a branch
            # selection. Keep the retrieval owner authoritative downstream.
            explicit_live_branch_return = False

        normalized_recovery_request = self._normalize_transition_text(user_input)
        interrupted_resume_request = any(marker in normalized_recovery_request for marker in (
            "انقطع", "انقطعت", "توقفنا", "اخر نقطه", "اخر نقطة",
            "دون ان اذكر اسم الموضوع", "بدون ان اذكر اسم الموضوع",
        ))
        explicit_independent_request = (
            not interrupted_resume_request
            and not prior_message_topic_question
            and not explicit_branch_return_request
            and (
                self._is_explicit_independent_topic(user_input, parsed)
                or self._is_explicit_topic_switch(user_input)
            )
        )
        if explicit_independent_request:
            # Do not let a generic interrupted-branch annotation turn an
            # explicitly independent technical explanation back into social chat.
            recovery_is_dialogue = False
            explanation_subject = self._explicit_explanation_topic(user_input)
            normalized_subject = self._normalize_transition_text(explanation_subject or "")
            cyber_subject_markers = (
                "sql injection", "csrf", "cross site request forgery", "xss",
                "cross site scripting", "ssrf", "xxe", "idor", "rce",
                "command injection", "path traversal", "directory traversal",
                "phishing", "malware", "ransomware", "session hijacking",
                "clickjacking", "sql",
            )
            current_intent = str(
                getattr((parsed or {}).get("intent"), "value", (parsed or {}).get("intent")) or ""
            ).casefold()
            current_domain = str((parsed or {}).get("conversation_domain") or "general").casefold()
            technical_independent = bool(
                explanation_subject
                and (
                    current_intent == "cyber_explain"
                    or current_domain == "technical"
                    or any(marker in normalized_subject for marker in cyber_subject_markers)
                )
            )
            if technical_independent:
                parsed = dict(parsed or {})
                parsed.update({
                    "intent": Intent.CYBER_EXPLAIN,
                    "target": explanation_subject,
                    "entity_type": "CONCEPT",
                    "conversation_domain": "technical",
                    "conversation_act": "EXECUTABLE_REQUEST",
                    "semantic_pattern": "EXPLICIT_INDEPENDENT_CYBER_EXPLANATION",
                    "source": "explicit_independent_topic",
                })
                attributes = dict(parsed.get("response_attributes") or {})
                attributes.pop("dialogue_recovery", None)
                parsed["response_attributes"] = attributes
                transition = ContextTransition.NEW_INDEPENDENT
                chat_history = []
        elif (
            explicit_branch_return_request
            and not prior_message_topic_question
            and not self._ordinal_dialogue_exchange(user_input)
        ):
            # Reassert a resolved named/previous topic only for an imperative
            # return. A bare reference such as "الموضوع السابق" remains REFERENCE.
            # heuristics. The selected branch's original intent/domain decide
            # whether it returns to the technical owner or live dialogue.
            resolved_topic = self._resolve_generic_topic_reference(user_input)
            if resolved_topic and self.dialogue_memory:
                normalized_topic = self._normalize_transition_text(resolved_topic)
                archive = getattr(
                    getattr(self.dialogue_memory, "state", None),
                    "exchange_archive",
                    [],
                ) or []
                restored_exchange = next((
                    item for item in reversed(archive)
                    if isinstance(item, dict)
                    and (
                        self._normalize_transition_text(item.get("target") or "") == normalized_topic
                        or self._normalize_transition_text(item.get("user") or "") == normalized_topic
                    )
                    and not item.get("recall_only")
                    and not item.get("state_boundary_only")
                    and str(item.get("context_transition") or "").casefold()
                        not in {"restore", "resume", "continue", "topic_return"}
                ), None)
                if restored_exchange:
                    restored_intent = str(restored_exchange.get("intent") or "").casefold()
                    restored_domain = str(
                        restored_exchange.get("conversation_domain") or "general"
                    ).casefold()
                    restored_kind = str(
                        restored_exchange.get("context_kind") or "dialogue"
                    ).casefold()
                    restored_user = self._normalize_transition_text(
                        restored_exchange.get("user") or ""
                    )
                    explicit_social_branch = any(marker in restored_user for marker in (
                        "موضوع عام", "نقاش عام", "حديث عام", "حوار عام",
                        "دعنا نتحدث", "لنتحدث", "نتحدث عن",
                    ))
                    restored_social = bool(restored_exchange) and (
                        explicit_social_branch or (
                            restored_kind in {"dialogue", "social", "unknown"}
                            and restored_domain not in {
                                "technical", "project", "work", "system", "execution",
                            }
                            and restored_intent not in {
                                "cyber_explain", "architecture", "propose_solution", "plan", "lab_plan",
                            }
                        )
                    )
                    parsed = dict(parsed or {})
                    parsed.update({
                        "intent": Intent.PERSONAL_CHAT if restored_social else (
                            Intent.CYBER_EXPLAIN if restored_intent == "cyber_explain" else restored_intent
                        ),
                        "target": resolved_topic,
                        "entity_type": "REFERENCE" if restored_social else "CONCEPT",
                        "conversation_domain": "general" if restored_social else (
                            "technical" if restored_domain == "general" else restored_domain
                        ),
                        "conversation_act": "TOPIC_RETURN",
                        "semantic_pattern": "RESOLVED_DIALOGUE_BRANCH_RETURN",
                        "source": "dialogue_branch_archive",
                    })
                    attributes = dict(parsed.get("response_attributes") or {})
                    attributes.pop("dialogue_recovery", None)
                    parsed["response_attributes"] = attributes
                    transition = ContextTransition.RESTORE
                    recovery_is_dialogue = False

        recovery_domain = str((parsed or {}).get("conversation_domain") or "general").casefold()
        recovery_intent = str(
            getattr((parsed or {}).get("intent"), "value", (parsed or {}).get("intent")) or ""
        ).casefold()
        recovery_is_social = (
            recovery_domain not in {"technical", "project", "work", "system", "execution"}
            and recovery_intent not in {
                "cyber_explain", "architecture", "propose_solution", "plan", "lab_plan",
            }
        )
        recovery_has_selected_target = bool(str((parsed or {}).get("target") or "").strip())
        route_override = (
            "L-LIVE" if interrupted_resume_request and not explicit_independent_request
            else "CLARIFY" if ambiguous_resume
            else "L-LIVE" if recovery_is_dialogue and (
                not recovery_has_selected_target or recovery_is_social
            )
            else "L-FACT" if local_project_answer is not None
            else None
        )
        # Canonical semantic request follows the context-authorized parse and
        # is established before selecting the execution owner.
        semantic = build_semantic_request(
            user_input,
            mode,
            intent=getattr(parsed.get("intent"), "value", parsed.get("intent")),
            conversation_domain=parsed.get("conversation_domain", "general"),
            conversation_act=conversation_act,
            conversation_confidence=float(
                parsed.get("conversation_confidence", 0.0) or 0.0
            ),
            response_attributes=parsed.get("response_attributes") or {},
            confidence=(
                float(parsed.get("confidence", 0.0))
                if parsed else 0.0
            ),
            target=(
                parsed.get("target")
                or (
                    context_entity.get("entity")
                    if context_entity and transition.value in CONTEXTUAL_TRANSITIONS
                    else None
                )
            ),
            requires_context=(transition.value in CONTEXTUAL_TRANSITIONS),
            context_transition=transition,
            context_kind=self._context_kind(user_input, parsed, transition),
        )

        route_decision = self.finalize_route(
            parsed=parsed,
            selected_session=selected_session,
            saved_session_request=saved_session_request,
            selected_saved_session_id=selected_saved_session_id,
            transition=transition,
            route_override=route_override,
        )
        parsed = dict(parsed or {})
        parsed["route_decision"] = route_decision
        parsed["output_kind"] = route_decision.output_kind
        self.context_lock = route_decision.context_lock

        if (
            route_decision.route == "CLARIFY"
            and route_decision.metadata.get("clarification_reason") == "missing_live_evidence"
        ):
            history_result = self._conversation_history_answer(user_input, parsed)
            if history_result is None and dialogue_memory_search_request:
                state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
                session_id = str(getattr(state, "session_id", "") or "")
                exchanges = [
                    item for item in (getattr(state, "exchange_archive", []) or [])
                    if isinstance(item, dict)
                    and (
                        not session_id
                        or not str(item.get("session_id") or "").strip()
                        or str(item.get("session_id") or "") == session_id
                    )
                    and not item.get("recall_only")
                    and not item.get("state_boundary_only")
                    and str(item.get("context_kind") or "dialogue").casefold()
                        not in {"work", "system"}
                    and str(item.get("conversation_domain") or "general").casefold()
                        not in {"work", "system", "execution"}
                    and str(item.get("user") or "").strip()
                    and str(item.get("assistant") or "").strip()
                ]
                if exchanges:
                    history_result = self._answer_dialogue_history(
                        user_input, "summary", exchanges[-6:]
                    )
                    history_result["source"] = "dialogue_memory"
                    history_result["dialogue_response_mode"] = "summary"
            if history_result is None:
                history_result = {
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": "لا توجد تبادلات حوارية مكتملة في الجلسة الحالية يمكن استرجاعها.",
                    "executed": False,
                }
            history_result["semantic_request"] = semantic.as_dict()
            return self._attach_route_decision(history_result, route_decision)

        if ambiguous_resume:
            return self._attach_route_decision({
                "status": "needs_clarification",
                "intent": parsed.get("intent") or Intent.RESUME,
                "source": "conversation_manager",
                "text": "هل تريد استكمال الحوار السابق أم استكمال العمل في جلسة أو ملف؟",
                "executed": False,
                "semantic_request": semantic.as_dict(),
            }, route_decision)

        # A generic return with no recoverable dialogue branch must fail
        # closed instead of being treated as a successful chat response.
        if raw_act == "TOPIC_RETURN" and not generic_topic and not _restore_context and self.dialogue_memory:
            state = getattr(self.dialogue_memory, "state", None)
            has_dialogue = bool(
                getattr(state, "history", [])
                or getattr(state, "exchange_archive", [])
                or getattr(state, "context_history", [])
                or getattr(state, "last_topic", None)
            )
            if not has_dialogue:
                return self._attach_route_decision({
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": "لا يوجد موضوع سابق مسجل أستطيع الرجوع إليه في هذه الجلسة. اذكر الموضوع الذي تريد استعادته.",
                    "executed": False,
                    "semantic_request": semantic.as_dict(),
                }, route_decision)

        # Strong project-progress requests must be resolved before broad
        # dialogue-history rules see words such as "كنا". This is still a
        # project-state read, not a dialogue-memory summary. Explicit saved
        # session restores and explicitly requested general scopes keep their
        # existing owners.
        # Project progress is a local knowledge request, not generic chat or dialogue recall.
        # Resolve scope from the current turn plus an already-authorized active branch.
        if (
            local_project_answer is not None
            and route_decision.route == "L-FACT"
            and not saved_session_request
            and not _restore_context
        ):
            # Anchor the saved branch to the actual project, not a stale technical target
            # inherited by a parser fallback on a short continuation.
            from dataclasses import replace as dataclass_replace
            project_parsed = dict(parsed or {})
            project_parsed.update({
                "target": "CyberLab Agent",
                "entity_type": "PROJECT",
                "conversation_domain": "project",
            })
            project_semantic = dataclass_replace(
                semantic,
                conversation_domain="project",
                context_kind="project",
                target="CyberLab Agent",
            )
            local_project_answer["semantic_request"] = project_semantic.as_dict()
            local_project_answer = self._finalize_local_dialogue_result(
                local_project_answer, mode, project_parsed, project_semantic
            )
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, local_project_answer, mode=mode, parsed=project_parsed,
                    context_transition=transition,
                )
            return self._attach_route_decision(local_project_answer, route_decision)


        # Ownership is decided before any generic/local responder. A history
        # query must never fall through to clarification, social chat, generic
        # topic resolution, or the LLM merely because the memory renderer has
        # no matching branch. An empty/insufficient archive is still a memory
        # answer with a memory-owned source.
        explicit_topic_reference = self._resolve_generic_topic_reference(user_input)
        named_topic_return = bool(re.search(
            r"(?:قلت|اقصد|المقصود)\s+(?:موضوع\s+)?(?:الكتب|كتب|الفن|الرسم|النحت)",
            self._normalize_transition_text(user_input),
        ))
        normalized_history_request = self._normalize_transition_text(user_input)
        history_output_request = (
            prior_message_topic_question
            or dialogue_memory_search_request
            or (
                self._dialogue_recall_requested(user_input, parsed)
                and any(marker in normalized_history_request for marker in (
                "ماذا كنا نقول", "ماذا كنا نتحدث", "ما كنا نقول",
                "الردود السابقة", "الردود السابقه", "قبل قليل",
                "ملخص الحوار", "اكتب ملخص", "لخص الحوار",
                "مضمون الجلسة", "مضمون الجلسه", "محتوى الجلسة",
                    "محتوى الجلسه", "الموضوع الذي ناقشناه سابقا",
                ))
            )
        )
        # A request to print/summarize the dialogue archive outranks a vague
        # reference to "the topic". Only an actual named/ordinal topic return
        # should bypass the history renderer.
        specific_dialogue_return = bool(
            not history_output_request
            and (
                explicit_topic_reference
                or self._ordinal_dialogue_exchange(user_input)
                or named_topic_return
            )
        )
        if (
            (
                raw_act == "CONVERSATION_HISTORY_QUERY"
                or prior_message_topic_question
                or dialogue_memory_search_request
                or self._dialogue_recall_requested(user_input, parsed)
            )
            and route_decision.route == "L-LIVE"
            and not interrupted_recovery
            and not explicit_live_branch_return
            and not specific_dialogue_return
            and not saved_session_request
            and self._dialogue_archive_request_kind(user_input) not in {"text_summary", "mention"}
        ):
            history_result = self._conversation_history_answer(user_input, parsed)
            if history_result is None:
                history_result = {
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": (
                        "لا توجد بيانات كافية في ذاكرة الحوار للإجابة عن طلب الاسترجاع. "
                        "اذكر الموضوع أو اطلب ملخص الحوار الحالي."
                    ),
                    "executed": False,
                }
            history_result["semantic_request"] = semantic.as_dict()
            history_result = self._finalize_local_dialogue_result(
                history_result, mode, parsed, semantic
            )
            # Retrieval is read-only: do not archive the retrieval request as a
            # new dialogue exchange or make it the next active topic.
            return self._attach_route_decision(history_result, route_decision)

        # Keep the unified responder scoped to greetings and closings.
        # Social openings, casual dialogue, acknowledgements, continuations, and
        # history requests retain their established owners below; otherwise this
        # helper can bypass social finalization, archive ownership, or provider
        # failure recovery.
        unified_act = str(
            (parsed or {}).get("conversation_act")
            or semantic.conversation_act
            or ""
        ).strip().upper()
        local_unified = (
            answer_local_response(
                user_input,
                parsed,
                semantic.as_dict(),
                history=chat_history,
                context_entity=context_entity,
            )
            if not saved_session_request
            and route_decision.route == "L-SOCIAL"
            and unified_act in {
                "SOCIAL_GREETING",
                "SOCIAL_CLOSING",
            }
            else None
        )
        if local_unified is not None:
            local_unified["semantic_request"] = semantic.as_dict()
            local_unified = self._finalize_local_dialogue_result(
                local_unified, mode, parsed, semantic
            )
            if (
                local_unified.get("status") == "success"
                and self.dialogue_memory
                and hasattr(self.dialogue_memory, "update")
            ):
                self.dialogue_memory.update(
                    user_input, local_unified, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return self._attach_route_decision(local_unified, route_decision)

        # Explicit persisted-session requests belong to Orchestrator. A local
        # social responder may otherwise consume ASSISTANT_STATE_QUERY and
        # return a generic greeting/history answer before session restoration.
        social_history = chat_history
        if not social_history and not saved_session_request and self.dialogue_memory:
            # An opener may be classified as a new independent conversational
            # turn while still benefiting from recent same-session dialogue.
            # The local composer itself enforces domain boundaries so technical
            # and project history cannot leak into a general social reply.
            social_history = self._history_for_transition(
                ContextTransition.CONTINUE, parsed
            )
        local_social = (
            None
            if saved_session_request or route_decision.route not in {"L-SOCIAL", "L-LIVE"}
            else self._local_social_answer(
                user_input, parsed, history=social_history
            )
        )
        if local_social is not None:
            local_social["semantic_request"] = semantic.as_dict()
            local_social = self._finalize_local_dialogue_result(
                local_social, mode, parsed, semantic
            )
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, local_social, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return self._attach_route_decision(local_social, route_decision)

        # ----------------------------------------------------
        # أسئلة تاريخ الحوار تُجاب من DialogueMemory محليًا، لا من سياق
        # المشروع أو مزود النموذج.
        conversation_history_answer = (
            None
            if (
                route_decision.route != "L-LIVE"
                or generic_topic
                or _restore_context
                or saved_session_request
                or interrupted_recovery
                or explicit_live_branch_return
            )
            else self._conversation_history_answer(user_input, parsed)
        )
        if (
            conversation_history_answer is None
            and route_decision.route == "L-LIVE"
            and not _restore_context
            and not saved_session_request
            and self._dialogue_recall_requested(user_input, parsed)
            and not self._resolve_generic_topic_reference(user_input)
            and not explicit_live_branch_return
            and not self._ordinal_dialogue_exchange(user_input)
            and not re.search(
                r"(?:قلت|اقصد|المقصود)\s+(?:موضوع\s+)?(?:الكتب|كتب|الفن|الرسم|النحت)",
                self._normalize_transition_text(user_input),
            )
            and recovery_mode not in {
                "interrupted_branch", "named_topic_return", "ordinal_topic_return",
            }
        ):
            conversation_history_answer = {
                "status": "needs_clarification",
                "intent": Intent.MEMORY_DUMP,
                "source": "dialogue_memory",
                "text": (
                    "لا أجد موضوعًا حواريًا واضحًا لاستعادته في هذه الجلسة. "
                    "هل تقصد آخر موضوع تعليمي أم سياق العمل؟"
                ),
                "executed": False,
            }

        if conversation_history_answer is not None:
            result = conversation_history_answer
            result["semantic_request"] = semantic.as_dict()
            result = self._finalize_local_dialogue_result(
                result, mode, parsed, semantic
            )
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, result, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return self._attach_route_decision(result, route_decision)


        # ----------------------------------------------------
        # ONE execution owner.
        # ----------------------------------------------------
        result = self._dispatch(
            resolved_input,
            mode,
            parsed,
            user_question=user_input,
            chat_history=chat_history,
            context_transition=transition.value,
        )
        selected_output_kind = route_decision.output_kind
        if selected_output_kind != "none":
            result["output_kind"] = selected_output_kind
        elif route_decision.route == "L-SESSION":
            result.pop("output_kind", None)
        if (
            result.get("context_action") == "read_only_report"
            and str(result.get("session_id") or "").strip()
        ):
            self.active_report_session_id = str(result["session_id"]).strip()
            self.active_report_topic_filter = (
                result.get("topic_filter")
                or (parsed.get("session_selector") or {}).get("topic_filter")
            )
        elif not active_report_followup and result.get("status") == "success":
            self.active_report_session_id = None
            self.active_report_topic_filter = None

        # Project-list clarification is conversation-owned state.
        if self.dialogue_memory:
            state = getattr(self.dialogue_memory, "state", None)
            if state is not None:
                if (
                    result.get("status") == "needs_clarification"
                    and parsed.get("intent") == Intent.PROJECT_INDEX
                    and any(
                        term in str(user_input)
                        for term in (
                            "المشاريع",
                            "مشاريع",
                            "اسماء",
                            "أسماء",
                            "اسماؤ",
                            "أسماؤ",
                        )
                    )
                ):
                    state.pending_clarification = {
                        "kind": "project_order",
                        "request": user_input,
                    }

        result = dict(result)
        result["semantic_request"] = semantic.as_dict()
        result["route_decision"] = route_decision

        # Saving an explanation is only offered for an actual technical
        # explanation response. Never leak a knowledge-save prompt into casual
        # chat, dialogue recall, or other non-executable conversation turns.
        if (
            semantic.context_kind in {"social", "dialogue"}
            or parsed.get("intent") == Intent.PERSONAL_CHAT
        ):
            result.pop("save_prompt", None)
            result.pop("pending_save", None)
            pending_confirmation = result.get("pending_confirmation")
            if (
                isinstance(pending_confirmation, dict)
                and pending_confirmation.get("kind") == "save_kb"
            ):
                result.pop("pending_confirmation", None)

        # ----------------------------------------------------
        # Presentation layer only.
        # ----------------------------------------------------
        if result.get("text"):
            result["text"] = format_response(
                result["text"],
                mode,
            )

        if self.dni:
            self.dni.set_conversation_analysis({
                "intent": result.get("intent"),
                "mode": result.get("mode", mode),
                "conversation_domain": semantic.conversation_domain,
                "conversation_act": semantic.conversation_act,
                "response_attributes": dict(semantic.response_attributes or {}),
                "confidence": (
                    parsed.get("confidence", 0.0)
                    if parsed else 0.0
                ),
            })

        # ConversationManager owns dialogue-state lifecycle.
        # Agent remains only the runtime facade.
        if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
            # Topic/user-turn state must survive provider failures. DialogueMemory
            # archives only successful answers; an error response must not become
            # a fabricated continuation checkpoint.
            self.dialogue_memory.update(
                user_input,
                result,
                mode=mode,
                parsed=parsed,
                context_transition=transition,
            )

        return result

    def _finalize_local_dialogue_result(
        self,
        result: dict,
        mode: str,
        parsed: dict,
        semantic,
    ) -> dict:
        """Apply the shared presentation and analysis contract to local dialogue replies."""
        result = dict(result)
        output_kind = str((parsed or {}).get("output_kind") or "").strip()
        if output_kind:
            result.setdefault("output_kind", output_kind)
        response_attributes = dict(
            result.get("response_attributes")
            or getattr(semantic, "response_attributes", {})
            or {}
        )
        if response_attributes:
            result["response_attributes"] = response_attributes
            response_mode = response_attributes.get("dialogue_response_mode")
            if response_mode and not result.get("dialogue_response_mode"):
                result["dialogue_response_mode"] = response_mode
        if (
            semantic.context_kind in {"social", "dialogue"}
            or parsed.get("intent") == Intent.PERSONAL_CHAT
        ):
            result.pop("save_prompt", None)
            result.pop("pending_save", None)
            pending_confirmation = result.get("pending_confirmation")
            if (
                isinstance(pending_confirmation, dict)
                and pending_confirmation.get("kind") == "save_kb"
            ):
                result.pop("pending_confirmation", None)

        if result.get("text"):
            result["text"] = format_response(result["text"], mode)

        if self.dni:
            self.dni.set_conversation_analysis({
                "intent": result.get("intent"),
                "mode": result.get("mode", mode),
                "conversation_domain": semantic.conversation_domain,
                "conversation_act": semantic.conversation_act,
                "response_attributes": dict(semantic.response_attributes or {}),
                "confidence": (
                    parsed.get("confidence", 0.0)
                    if parsed else 0.0
                ),
            })
        return result

    def _dispatch(
        self,
        text: str,
        mode: str,
        parsed: dict,
        *,
        user_question: str | None = None,
        chat_history: list | None = None,
        context_transition: str | None = None,
    ) -> dict:
        """Dispatch through the single finalized RouteDecision owner.

        There is deliberately no parser/mode-based compatibility fallback here.
        Every production request reaches this boundary with the immutable route
        attached by process(); direct or legacy callers without that grant fail
        closed instead of selecting a second execution path.
        """
        intent = (parsed or {}).get("intent")
        route_decision = (parsed or {}).get("route_decision")
        if not isinstance(route_decision, RouteDecision):
            return {
                "status": "denied",
                "intent": intent,
                "source": "route_decision_required_at_dispatch",
                "executed": False,
                "text": "لا يمكن اختيار مسار بديل دون قرار التوجيه النهائي.",
            }

        route = route_decision.route
        if route == "DENY":
            return {
                "status": "denied", "intent": intent,
                "source": "route_decision", "executed": False,
                "text": "هذا الطلب غير مسموح ضمن قرار التوجيه الحالي.",
                "route_decision": route_decision,
            }
        if route == "CLARIFY":
            return {
                "status": "needs_clarification", "intent": intent,
                "source": "route_decision", "executed": False,
                "text": "يلزم تحديد السياق أو الجلسة المقصودة قبل المتابعة.",
                "route_decision": route_decision,
            }
        if (
            route in {"L-SOCIAL", "L-LIVE"}
            and intent in (Intent.UNSUPPORTED, "unsupported")
            and (parsed or {}).get("semantic_pattern") == "DEVICE_MEMORY_UNSUPPORTED"
        ):
            return {
                "status": "unsupported",
                "intent": intent,
                "source": "capability_boundary",
                "text": (
                    "قراءة ذاكرة RAM للهاتف أو الجهاز غير مدعومة من هذه البيئة. "
                    "فحص الصحة المتاح يقيس ذاكرة عملية الوكيل فقط."
                ),
                "mode": mode,
                "executed": False,
                "route_decision": route_decision,
            }
        if route in {"L-SOCIAL", "L-LIVE", "L-FACT"}:
            result = self._handle_chat(
                text, mode, parsed=parsed,
                user_question=user_question or text, history=chat_history,
            )
            result = dict(result or {})
            result.setdefault("executed", False)
            result["route_decision"] = route_decision
            return result
        if route in {"L-SESSION", "L-EXEC", "P-TOOL"}:
            result = self.orchestrator.handle(
                text,
                parsed=parsed,
                context_resolved=True,
                conversation_history=chat_history,
                context_transition=context_transition,
                route_decision=route_decision,
            )
            if not isinstance(result, dict):
                return {
                    "status": "error", "intent": intent,
                    "source": "route_decision_orchestrator_contract",
                    "executed": False,
                    "text": "أعاد مالك المسار نتيجة غير صالحة.",
                    "route_decision": route_decision,
                }
            result = dict(result)
            result["executed"] = (
                False if route == "L-SESSION"
                else result.get("status") not in {
                    "needs_clarification", "denied", "unsupported", "error", "failed",
                }
            )
            result["route_decision"] = route_decision
            return result

        return {
            "status": "denied",
            "intent": intent,
            "source": "route_decision_unknown_owner",
            "executed": False,
            "text": "قرار التوجيه لا يحدد مالكًا تنفيذيًا معتمدًا لهذا الطلب.",
            "route_decision": route_decision,
        }

    def _handle_chat(
        self,
        text: str,
        mode: str,
        *,
        parsed: dict | None = None,
        user_question: str | None = None,
        history: list | None = None,
    ) -> dict:
        result = {}
        try:
            intent = (parsed or {}).get("intent")
            response_attributes = (parsed or {}).get("response_attributes") or {}
            route_decision = (parsed or {}).get("route_decision")
            evidence_scope = str(
                getattr(route_decision, "evidence_scope", "none")
                if route_decision is not None else "none"
            )
            compound_request = bool(response_attributes.get("compound_request"))
            normalized_question = self._normalize_transition_text(user_question or text)
            general_scope_markers = (
                "بصفة عامة", "بشكل عام", "بصورة عامة", "عموما",
                "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
                "خارج بنية المشروع", "خارج نبية المشروع",
                "لا نتحدث عن مشروع", "لا نتحدث عن مشروع cyberlab",
                "ليس عن مشروع", "بلا علاقة بالمشروع",
            )
            explicitly_general_scope = any(
                marker in normalized_question for marker in general_scope_markers
            )
            # One compound message belongs to the ordinary conversational responder.
            # Do not inject agent-self or project knowledge because individual items
            # mention the agent, Python, or project-adjacent vocabulary.
            self_knowledge = (
                build_agent_self_knowledge(intent)
                if intent in _AGENT_SELF_INTENTS
                and not compound_request
                and not explicitly_general_scope
                else None
            )
            scope_question = " ".join(
                part for part in (
                    str(user_question or text),
                    str((parsed or {}).get("target") or ""),
                ) if part
            )
            project_scope = (
                "general"
                if compound_request or explicitly_general_scope
                else resolve_project_scope(scope_question, intent=intent)
            )
            authorized_project_context = False
            context_domain = str(
                (parsed or {}).get("conversation_domain") or ""
            ).casefold()
            # A project branch is explicit authorization to resolve an
            # otherwise ambiguous follow-up against this project. It cannot
            # override a question explicitly scoped as generic, external, or
            # historical, nor a compound/general conversation.
            if (
                not compound_request
                and not explicitly_general_scope
                and context_domain == "project"
                and project_scope not in {
                    ProjectScope.EXTERNAL_PROJECT,
                    ProjectScope.GENERIC_PROJECT,
                    ProjectScope.HISTORICAL_PROJECT,
                }
            ):
                project_scope = ProjectScope.CURRENT_PROJECT
                authorized_project_context = True

            # Architecture is a knowledge type too; excluding it silently
            # sent layer questions to generic provider prose.
            project_knowledge = None
            knowledge_type = QuestionClassifier.classify(user_question or text)
            is_agent_capability_query = (
                intent == Intent.AGENT_CAPABILITIES or knowledge_type == "capability"
            )
            is_agent_architecture_query = intent in {
                Intent.AGENT_ARCHITECTURE,
                Intent.AGENT_EXECUTION_FLOW,
                Intent.AGENT_LIMITS,
            }
            if (
                not compound_request
                and user_question
                and (
                    (
                        is_agent_capability_query
                        and evidence_scope in {"project_state", "work_state"}
                    )
                    or (
                        not explicitly_general_scope
                        and project_scope == ProjectScope.CURRENT_PROJECT
                        and (
                            is_agent_architecture_query
                            or knowledge_type in {
                                "component", "relationship", "execution", "file",
                                "architecture",
                            }
                        )
                    )
                )
                and (route_decision is None or evidence_scope == "project_state")
            ):
                try:
                    authorize_agent_snapshot = (
                        is_agent_architecture_query
                        and not explicitly_general_scope
                        and project_scope != ProjectScope.CURRENT_PROJECT
                    )
                    if authorized_project_context or authorize_agent_snapshot:
                        project_knowledge = retrieve_for_question(
                            user_question,
                            authorized_current_project=True,
                            evidence_scope=evidence_scope,
                        )
                    else:
                        project_knowledge = retrieve_for_question(
                            user_question,
                            evidence_scope=evidence_scope,
                        )
                except Exception as exc:
                    # Preserve a truthful, evidence-empty result instead of
                    # silently falling through to an apparently grounded LLM
                    # answer.
                    project_knowledge = {
                        "type": knowledge_type,
                        "components": [],
                        "current_project_knowledge": True,
                        "retrieval_error": type(exc).__name__,
                        "recommendation": (
                            "تعذر استرجاع أدلة المشروع؛ صرّح بعدم كفاية الأدلة "
                            "ولا تستبدلها بوصف عام."
                        ),
                    }
            project_capability_scope = any(
                marker in normalize_text(user_question or text)
                for marker in (
                    "مشروع", "مشاريع", "مستودع", "مستودعات",
                    "ملف", "ملفات", "مجلد", "اختبار", "اختبارات",
                    "تعديل", "فحص", "شيفره", "كود",
                )
            )
            if (
                intent == Intent.AGENT_CAPABILITIES
                and project_capability_scope
                and isinstance(project_knowledge, dict)
                and project_knowledge.get("type") == "capability"
                and not project_knowledge.get("retrieval_error")
            ):
                local_capability = answer_local_response(
                    user_question or text,
                    parsed,
                    {
                        "intent": getattr(intent, "value", intent),
                        "conversation_domain": (parsed or {}).get("conversation_domain", "agent_self"),
                        "conversation_act": (parsed or {}).get("conversation_act", "ASSISTANT_CAPABILITY_QUERY"),
                        "target": (parsed or {}).get("target") or "",
                        "response_attributes": response_attributes,
                    },
                    history=list(history or []),
                    context_entity=project_knowledge,
                )
                if local_capability is not None:
                    local_capability = dict(local_capability)
                    local_capability.update({
                        "mode": mode,
                        "source": "local_capability_evidence",
                        "provider_used": False,
                        "evidence_scope": evidence_scope,
                        "executed": False,
                    })
                    if isinstance(route_decision, RouteDecision):
                        return self._attach_route_decision(local_capability, route_decision)
                    return local_capability

            system, prompt = build_chat_prompt(
                text,
                list(history or []),
                agent_self_knowledge=self_knowledge,
                project_knowledge=project_knowledge,
                project_scope=project_scope,
                conversation_semantics={
                    "intent": getattr(
                        (parsed or {}).get("intent"),
                        "value",
                        (parsed or {}).get("intent"),
                    ),
                    "conversation_domain": (parsed or {}).get(
                        "conversation_domain", "general"
                    ),
                    "conversation_act": (parsed or {}).get(
                        "conversation_act", "NONE"
                    ),
                    "response_attributes": (parsed or {}).get(
                        "response_attributes", {}
                    ),
                },
            )
            if (parsed or {}).get("response_attributes", {}).get("compound_request"):
                system = str(system or "") + (
                    "\n\nتعليمات للطلب المركب: أجب عن كل بند مرقّم بالترتيب نفسه، "
                    "ولا تسقط أي بند حتى لو تكرر سياقه. ميّز بوضوح بين الحديث الودي "
                    "والسؤال التقني وتصحيح الافتراض الخاطئ. صحّح الافتراضات الخاطئة "
                    "بشرح موجز، ولا تستبدل الإجابة المطلوبة بشرح عن بنية الوكيل أو "
                    "قدراته إلا إذا كان ذلك بندًا صريحًا في السؤال."
                )

            route_decision = (parsed or {}).get("route_decision")
            result = (
                gateway_ask(
                    prompt,
                    system=system,
                    # Reasoning can consume the full budget before GPT-5 emits
                    # visible text; grounded self-descriptions need extra headroom.
                    max_tokens=4000 if self_knowledge else 1600,
                    temperature=0.7,
                    routing_text=text,
                    provider_allowed=True,
                )
                if route_decision is not None and bool(
                    getattr(route_decision, "provider_allowed", False)
                ) else {"status": "unavailable", "message": "provider denied by RouteDecision"}
            )

            if result.get("status") != "success":
                raise RuntimeError(
                    result.get("message")
                )

            reply = result.get("text", "")

            if not reply:
                raise ValueError("empty")

            if self_knowledge:
                reply = self._bound_agent_self_reply(
                    reply,
                    (parsed or {}).get("intent"),
                    user_question or text,
                    fallback=self_knowledge,
                )

            return {
                "status": "success",
                "intent": (parsed or {}).get("intent", mode.lower()),
                "text": reply,
                "mode": mode,
                "source": "llm",
                "provider_used": result.get("provider_used"),
                "provider_chain": result.get(
                    "provider_chain",
                    [],
                ),
                "model": result.get("model"),
                "executed": False,
            }

        except Exception as e:
            gateway_error = (
                result.get("error")
                if isinstance(result, dict)
                else None
            )

            # Project-scoped questions remain owned by local project knowledge
            # when generation is unavailable. Return an explicit evidence gap
            # instead of an opaque provider error or an invented file description.
            if project_scope == ProjectScope.CURRENT_PROJECT and not compound_request:
                knowledge_available = bool(
                    isinstance(project_knowledge, dict)
                    and any(
                        project_knowledge.get(key)
                        for key in (
                            "components", "relationships", "files", "entities",
                            "architecture", "facts", "evidence",
                        )
                    )
                )
                if knowledge_available:
                    project_reply = (
                        "تعذر تركيب إجابة موثقة من أدلة المشروع المحلية في هذه المحاولة. "
                        "السجل المسترجع مرتبط بالمشروع، لكنه لا يثبت وحده الوظيفة المطلوبة. "
                        "لن أستنتج وظيفة الملف من اسمه فقط."
                    )
                else:
                    project_reply = (
                        "لا تتوفر في قاعدة المعرفة المحلية أدلة كافية للإجابة عن هذا السؤال "
                        "حول المشروع أو الملف المحدد. لم أستبدل نقص الأدلة بوصف تخميني. "
                        "يمكن تحديد الملف أو الجزء المطلوب بدقة أكبر لاسترجاع مصدره."
                    )
                return {
                    "status": "needs_clarification",
                    "intent": (parsed or {}).get("intent", mode.lower()),
                    "target": (parsed or {}).get("target") or "",
                    "text": project_reply,
                    "mode": mode,
                    "source": "local_project_knowledge",
                    "provider_failure_code": (
                        str(gateway_error.get("code") or "")
                        if isinstance(gateway_error, dict) else ""
                    ),
                    "executed": False,
                }

            # If generation is unavailable, use the bounded local composer for
            # ordinary conversation continuations. It quotes only the authorized
            # dialogue history and explicitly labels the result as local; it
            # cannot answer project, operational, or unsupported factual turns.
            local_intent = str(
                getattr((parsed or {}).get("intent"), "value", (parsed or {}).get("intent")) or ""
            ).casefold()
            local_act = str((parsed or {}).get("conversation_act") or "").upper()
            local_domain = str((parsed or {}).get("conversation_domain") or "general").casefold()
            # Social openings/follow-ups can be composed locally after a
            # provider failure. A continuation is eligible only when the local
            # responder classifies the authorized history as social-only and
            # returns the explicit friendly-reopen strategy. A real topic must
            # retain the safe last-point recovery below rather than pretending
            # that quoting its previous answer is a new continuation.
            local_fallback_acts = {
                "SOCIAL_OPENING", "CASUAL_CONVERSATION", "CASUAL_DISCUSSION",
                "PERSONAL_INTERACTION", "SOCIAL_FOLLOW_UP",
                "CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY",
            }
            local_history = list(history or [])
            local_history_is_dialogue = bool(local_history) and all(
                isinstance(turn, dict)
                and str(turn.get("conversation_domain") or "general").casefold()
                    in {"", "general", "social"}
                and str(turn.get("context_kind") or "dialogue").casefold()
                    not in {"work", "system", "execution"}
                for turn in local_history
            )
            if (
                local_intent in {"personal_chat", "discussion", "chat"}
                and local_domain in {"", "general", "social"}
                and local_act in local_fallback_acts
                and local_history_is_dialogue
            ):
                local_semantic = {
                    "conversation_act": local_act,
                    "conversation_domain": local_domain or "general",
                    "target": (parsed or {}).get("target") or "",
                    "response_attributes": (parsed or {}).get("response_attributes") or {},
                }
                local_result = answer_local_response(
                    user_question or text,
                    parsed,
                    local_semantic,
                    history=list(history or []),
                )
                if local_result is not None:
                    local_result = dict(local_result)
                    is_continuation = local_act in {
                        "CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY",
                    }
                    if (
                        is_continuation
                        and local_result.get("local_strategy") != "friendly_dialogue_reopen"
                    ):
                        # Preserve the established truthful recovery for a real
                        # topic when no provider can generate the next content.
                        local_result = None
                    if local_result is not None:
                        local_result["source"] = "local_dialogue_fallback"
                        local_result["mode"] = mode
                        local_result["executed"] = False
                        local_result["recovery"] = "provider_unavailable_local_dialogue"
                        local_result["provider_failure_code"] = (
                            str(gateway_error.get("code") or "")
                            if isinstance(gateway_error, dict)
                            else ""
                        )
                        if local_result.get("local_strategy") != "friendly_dialogue_reopen":
                            local_result["text"] = str(local_result.get("text") or "").rstrip() + (
                                "\n\nملاحظة: تعذر الحصول على رد من المزود؛ هذه متابعة محلية "
                                "مبنية على الحوار المحفوظ، وليست شرحًا جديدًا يعتمد على معرفة خارجية."
                            )
                        return local_result

            continuation = str((parsed or {}).get("conversation_act") or "").upper() in {
                "CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY",
            }
            branch = None
            if self.dialogue_memory:
                get_branch = getattr(self.dialogue_memory, "active_dialogue_branch", None)
                branch = get_branch() if callable(get_branch) else None
            explicit_resume_topic = self._explicit_resume_topic(text)
            if continuation and (branch or explicit_resume_topic):
                # Prefer a subject explicitly named in the current turn. A
                # stale active branch must never replace "space" with a prior
                # acknowledgement such as "good".
                topic = explicit_resume_topic or str(branch.get("entity") or "").strip()
                last_point = ""
                matching_exchanges = []
                if explicit_resume_topic and self.dialogue_memory:
                    state = getattr(self.dialogue_memory, "state", None)
                    session_id = str(getattr(state, "session_id", "") or "")
                    normalized_topic = self._normalize_transition_text(explicit_resume_topic)
                    matching_exchanges = [
                        item for item in (getattr(state, "exchange_archive", []) or [])
                        if isinstance(item, dict)
                        and (not session_id or str(item.get("session_id") or "") == session_id)
                        and not item.get("recall_only")
                        and not item.get("state_boundary_only")
                        and str(item.get("context_kind") or "").casefold()
                            not in {"work", "system", "execution"}
                        and (
                            normalized_topic in self._normalize_transition_text(item.get("target") or "")
                            or normalized_topic in self._normalize_transition_text(item.get("user") or "")
                        )
                    ]
                if explicit_resume_topic and matching_exchanges:
                    from lab_v4_dev.memory.session_state import summarize_dialogue_exchanges
                    report = summarize_dialogue_exchanges(
                        matching_exchanges[-4:],
                        topic=explicit_resume_topic,
                        limit=2,
                    )
                    last_point = report["insights"][-1] if report["insights"] else ""
                elif not explicit_resume_topic and branch:
                    last_point = str(branch.get("reference_text") or "").strip()

                details = []
                if topic:
                    details.append(f"الموضوع المطلوب متابعته: {topic}.")
                if explicit_resume_topic and not matching_exchanges:
                    details.append(
                        "لا توجد نقطة سابقة موثقة لهذا الموضوع في الحوار الجاري؛ "
                        "لم أخلطه بموضوع آخر محفوظ."
                    )
                    details.append(
                        "يمكنك بدء نقاش جديد حوله أو تحديد الجلسة المحفوظة التي تريد استرجاعها."
                    )
                else:
                    if last_point:
                        details.append(f"آخر نقطة محفوظة في هذا الفرع: {last_point}")
                    details.append(
                        "تعذر توليد شرح جديد لأن المزود غير متاح في هذه المحاولة. "
                        "حافظت على حدود السجل ولم أختلق محتوى جديدًا. "
                        "يمكنك طلب تلخيص النقاط المحفوظة أو إعادة المحاولة لاحقًا."
                    )
                return {
                    "status": "needs_clarification",
                    "intent": (parsed or {}).get("intent", mode.lower()),
                    "text": "\n".join(details),
                    "mode": mode,
                    "source": "dialogue_memory",
                    "gateway_error": gateway_error,
                    "recovery": (
                        "explicit_topic_not_in_live_dialogue"
                        if explicit_resume_topic and not matching_exchanges
                        else "provider_unavailable_preserved_dialogue"
                    ),
                    "executed": False,
                }
            error_code = (
                str(gateway_error.get("code") or "").strip()
                if isinstance(gateway_error, dict)
                else ""
            )
            if error_code == "PRIVACY_EXTERNAL_BLOCKED":
                fallback = (
                    "حُجب إرسال هذا الطلب إلى مزود خارجي وفق فحص الخصوصية. "
                    "لم يُنفَّذ أي إجراء، ولم يُسجَّل رد مختلق."
                )
            elif error_code == "NO_PROVIDER_AVAILABLE":
                fallback = (
                    "لا يوجد حاليًا مزود ذكاء اصطناعي مهيأ ومتاح لإنتاج الرد. "
                    "لم أتمكن من متابعة الحوار في هذه المحاولة."
                )
            elif error_code == "TIMEOUT":
                fallback = (
                    "انتهت مهلة انتظار مزود الذكاء الاصطناعي قبل وصول رد صالح. "
                    "لم أتمكن من متابعة الحوار في هذه المحاولة."
                )
            elif error_code:
                fallback = (
                    "تعذر إنتاج رد صالح من مزود الذكاء الاصطناعي "
                    f"(رمز الخطأ: {error_code}). لم أعتبر رسالة الخطأ إجابة "
                    "ولم أضفها إلى سجل الحوار كأنها رد ناجح."
                )
            else:
                fallback = (
                    "تعذر إنتاج رد صالح في هذه المحاولة. لا تتوفر أدلة كافية "
                    "للجزم بأن السبب هو الاتصال أو إعدادات المزود."
                )

            return {
                "status": "error",
                "intent": (parsed or {}).get("intent", mode.lower()),
                "text": fallback,
                "mode": mode,
                "source": "fallback",
                "provider_used": (
                    result.get("provider_used")
                    if isinstance(result, dict)
                    else None
                ),
                "provider_chain": (
                    result.get("provider_chain", [])
                    if isinstance(result, dict)
                    else []
                ),
                "model": (
                    result.get("model")
                    if isinstance(result, dict)
                    else None
                ),
                "gateway_error": gateway_error,
                "error": error_code or str(e) or type(e).__name__,
                "executed": False,
            }

    def switch_topic(
        self,
        current_topic: str,
        new_input: str,
    ) -> dict:
        if self.dialogue_memory:
            self.dialogue_memory.save_pending(
                current_topic
            )

        return self.process(new_input)

    def restore_topic(self) -> dict:
        if self.dialogue_memory:
            topic = getattr(self.dialogue_memory, "pending_topic", None)
            if topic:
                context = getattr(self.dialogue_memory.state, "pending_context", None)
                if not isinstance(context, dict) or not context.get("entity"):
                    context = self.dialogue_memory.context_for_topic(topic)
                if not context:
                    return {
                        "status": "needs_clarification",
                        "intent": Intent.MEMORY_DUMP,
                        "source": "dialogue_memory",
                        "text": "لا أجد فرعًا محفوظًا موثوقًا لهذا الموضوع؛ لم أغيّر الموضوع النشط.",
                        "executed": False,
                    }
                result = dict(
                    self.process(
                        "استعادة الفرع الحواري المحفوظ",
                        _restore_context=context,
                    )
                )
                self.dialogue_memory.restore_pending()
                result.setdefault("topic", topic)
                result.setdefault("target", topic)
                semantic_request = result.get("semantic_request")
                if isinstance(semantic_request, dict):
                    semantic_request.setdefault("target", topic)
                    semantic_request.setdefault("context_transition", "restore")
                return result

        return {
            "status": "success",
            "intent": "topic_restore",
            "text": "لا يوجد موضوع مؤجل.",
        }
