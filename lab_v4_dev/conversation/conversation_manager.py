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
    -> sole execution owner for executable Intent.

LLM
    -> direct conversational responder only when IntentParser resolves
       no executable operation.

Important:
FOLLOW_UP is a conversational MODE, not an automatic LLM route.
If IntentParser resolves a FOLLOW_UP to an executable Intent
(e.g. CYBER_EXPLAIN), that Intent goes to Orchestrator.
"""

from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.conversation.assistant_style import format_response, single_question
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
from lab_v4_dev.nlu.context_resolver import is_incomplete
from lab_v4_dev.nlu.conversation_semantics import (
    classify_conversation_semantics,
    is_social_act,
    is_style_act,
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
        if transition != ContextTransition.NEW_INDEPENDENT or (parsed or {}).get("target"):
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
        return any(normalized.startswith(prefix) for prefix in explicit_starts)

    def process(self, user_input: str) -> dict:
        # Session boundaries take precedence over pending clarifications and all
        # NLU/context resolution. A new dialogue must never inherit old state.
        if self._is_new_dialogue_session_request(user_input):
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
            return {
                "status": "success",
                "intent": Intent.RESTART,
                "source": "conversation_manager",
                "text": "بدأت جلسة حوار جديدة ومستقلة. لم أستعد سياق الجلسة السابقة.",
                "executed": False,
            }

        # Consume an existing project-list ordering clarification
        # before treating "1/2/3" as a new independent request.
        if self.dialogue_memory:
            pending = getattr(
                getattr(self.dialogue_memory, "state", None),
                "pending_clarification",
                None,
            )
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
                    self.dialogue_memory.state.pending_clarification = None
                    user_input = f"{base_request} {order}".strip()

        mode = detect_mode(user_input)
        # A direct stop request is a conversation control, not an executable
        # task. Do not send it through the parser fallback or Orchestrator.
        if self._is_explicit_stop_request(user_input):
            return {
                "status": "success",
                "intent": Intent.STOP,
                "source": "conversation_manager",
                "text": "سأتوقف عن متابعة الطلب الحالي؛ لم أرسل أمر إلغاء إلى أي مهمة تنفيذية.",
                "executed": False,
            }

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
            else self._safe_parse(user_input)
        )
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
            return {
                "status": "needs_clarification",
                "intent": Intent.VERIFY_FIX,
                "source": "conversation_manager",
                "text": (
                    "ما الذي تريدني أن أتحقق منه تحديدًا؟ "
                    "اذكر الإصلاح أو الاختبار أو المعلومة المقصودة."
                ),
                "executed": False,
            }

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
        from lab_v4_dev.memory.session_state import session_selector
        selected_session = session_selector(user_input)
        if selected_session.get("kind") != "none":
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
        # The raw semantic signal is an authority boundary: a dialogue-history
        # or continuation turn must not be hijacked by HISTORY/CONTEXT_REPORT/
        # RESUME parser fallbacks before DialogueMemory sees it.
        raw_signal = classify_conversation_semantics(user_input)
        explicit_topic = self._explicit_dialogue_topic(user_input)
        if explicit_topic:
            # Explicit topic openings create a dialogue branch even if the LLM
            # provider later fails. The old branch is not inherited as context.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": explicit_topic,
                "entity_type": "CONCEPT",
                "conversation_domain": "technical",
                "conversation_act": "SOCIAL_OPENING",
                "conversation_confidence": 0.95,
                "semantic_pattern": "EXPLICIT_DIALOGUE_TOPIC",
                "source": "explicit_dialogue_topic",
            })
        explicit_explanation = self._explicit_explanation_topic(user_input)
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
        raw_act = raw_signal.get("conversation_act")
        interrupted_recovery = str(
            (raw_signal.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold() == "interrupted_branch"
        if raw_act in {
            "CONVERSATION_HISTORY_QUERY",
            "CONVERSATION_CONTINUATION",
            "TOPIC_RETURN",
        } and not explicit_explanation and not explicit_casual_opening:
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
                active_context = self.dialogue_memory.active_context_entity()
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
        generic_topic = (
            None
            if raw_act == "CONVERSATION_HISTORY_QUERY"
            or explicit_casual_opening
            or interrupted_recovery
            else self._resolve_generic_topic_reference(user_input)
        )
        if generic_topic:
            candidate = dict(candidate or {})
            is_ordinal_return = any(marker in str(user_input or "").casefold() for marker in (
                "الأول", "الاول", "الثاني", "الثانى", "first", "second",
                "ارجع", "عد إلى", "عد الى",
            ))
            candidate.update({
                "intent": Intent.CYBER_EXPLAIN,
                "target": generic_topic,
                "entity_type": "CONCEPT",
                "semantic_pattern": "GENERIC_TOPIC_REFERENCE",
                "conversation_domain": "technical",
                "conversation_act": (
                    "TOPIC_RETURN" if is_ordinal_return else "COMPOUND_REFERENCE"
                ),
                "conversation_confidence": 0.95,
            })
            # Re-activate the restored branch's canonical action. Otherwise
            # a prior semantic override can leave the return labelled as chat.
            if raw_act == "TOPIC_RETURN" and self.dialogue_memory:
                get_context = getattr(self.dialogue_memory, "context_for_topic", None)
                restored = get_context(generic_topic) if callable(get_context) else None
                restored_action = (
                    str(restored.get("action") or "").casefold()
                    if isinstance(restored, dict) else ""
                )
                # A saved branch can have a conversational placeholder action
                # (personal_chat) even though the topic was introduced as a
                # technical explanation. Never let that placeholder overwrite
                # the canonical intent resolved from the explicit topic return.
                if restored_action and restored_action not in {
                    "personal_chat", "chat", "discussion", "question", "unclear",
                }:
                    candidate["intent"] = restored["action"]
        transition = self._classify_context_transition(mode, candidate, text=user_input)
        if interrupted_recovery:
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
        if explicit_casual_opening and not explicit_explanation:
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
            # explicit subject after "اشرح/عن/حول" for the new branch.
            import re as _re
            independent_subject = _re.search(
                r"(?:اشرح|عن|حول|explain)\s+([^،,.؟?]+)",
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
                    candidate["intent"] = Intent.CYBER_EXPLAIN
                    candidate["entity_type"] = "CONCEPT"
                    candidate["conversation_domain"] = "technical"
            else:
                # Do not carry an inherited target into a new subjectless topic.
                candidate = dict(candidate or {})
                candidate["target"] = ""
                candidate["entity_type"] = "UNKNOWN"
                if not explicit_explanation:
                    candidate["intent"] = Intent.PERSONAL_CHAT
                    candidate["conversation_domain"] = "social"
        if selected_session.get("kind") != "none":
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
        self._clear_unrelated_execution_file(transition, candidate)
        resolved_input = user_input
        parsed = candidate
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
                if context_entity is None:
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

        style_request = is_style_act(candidate.get("conversation_act"))
        recovery_mode = str(
            (candidate.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        unnamed_branch_return = recovery_mode == "interrupted_branch"
        if (
            self.dialogue_memory
            and context_entity
            and transition.value in CONTEXTUAL_TRANSITIONS
            and not style_request
            and not unnamed_branch_return
            and (
                not candidate.get("target")
                or str(candidate.get("entity_type", "")).upper()
                in {"REFERENCE", "ELABORATION"}
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
            if resolved_input != user_input:
                parsed = self._safe_parse(
                    resolved_input,
                    context_entity=context_entity,
                )

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

        chat_history = self._history_for_transition(transition, parsed)

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

        # A generic return with no recoverable dialogue branch must fail
        # closed instead of being treated as a successful chat response.
        if raw_act == "TOPIC_RETURN" and not generic_topic and self.dialogue_memory:
            state = getattr(self.dialogue_memory, "state", None)
            has_dialogue = bool(
                getattr(state, "history", [])
                or getattr(state, "exchange_archive", [])
                or getattr(state, "context_history", [])
                or getattr(state, "last_topic", None)
            )
            if not has_dialogue:
                return {
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": "لا يوجد موضوع سابق مسجل أستطيع الرجوع إليه في هذه الجلسة. اذكر الموضوع الذي تريد استعادته.",
                    "executed": False,
                    "semantic_request": semantic.as_dict(),
                }

        local_social = self._local_social_answer(user_input, parsed)
        if local_social is not None:
            local_social["semantic_request"] = semantic.as_dict()
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, local_social, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return local_social

        # ----------------------------------------------------
        # أسئلة تاريخ الحوار تُجاب من DialogueMemory محليًا، لا من سياق
        # المشروع أو مزود النموذج.
        conversation_history_answer = (
            None
            if generic_topic
            else self._conversation_history_answer(user_input, parsed)
        )
        recovery_mode = str(
            (parsed.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        if (
            conversation_history_answer is None
            and self._dialogue_recall_requested(user_input, parsed)
            and not self._resolve_generic_topic_reference(user_input)
            and recovery_mode != "interrupted_branch"
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
        if self._ambiguous_resume_without_domain(user_input, parsed):
            return {
                "status": "needs_clarification",
                "intent": parsed.get("intent") or Intent.RESUME,
                "source": "conversation_manager",
                "text": (
                    "هل تريد استكمال الحوار السابق أم استكمال العمل في جلسة أو ملف؟"
                ),
                "executed": False,
                "semantic_request": semantic.as_dict(),
            }
        if conversation_history_answer is not None:
            result = conversation_history_answer
            result["semantic_request"] = semantic.as_dict()
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, result, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return result

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
        """
        Select exactly ONE execution owner.

        Critical rule:
        Mode is descriptive. Intent is authoritative.

        Therefore:
            FOLLOW_UP + executable Intent
                -> Orchestrator

            QUESTION/DISCUSSION/CHAT + executable Intent
                -> Orchestrator

            non-executable Intent
                -> conversational LLM
        """

        intent = parsed.get("intent") if parsed else None
        explicit_target = str((parsed or {}).get("target") or "").strip()

        # An unnamed interrupted-dialogue recovery is a conversational
        # continuation request. Keep its canonical restored intent/target for
        # memory bookkeeping, but send the selected archived branch to the
        # dialogue prompt instead of treating the recovery wording as a fresh
        # executable explanation request.
        recovery_mode = str(
            ((parsed or {}).get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        if recovery_mode == "interrupted_branch":
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        if (
            intent in _NON_EXECUTABLE_INTENTS
            and context_transition in CONTEXTUAL_TRANSITIONS
            and explicit_target
            and (parsed or {}).get("conversation_domain") == "project"
            and not is_style_act((parsed or {}).get("conversation_act"))
        ):
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.CYBER_EXPLAIN
            intent = Intent.CYBER_EXPLAIN

        # Agent self-description is grounded conversation, not a system action.
        # This check deliberately precedes SYSTEM mode dispatch.
        if intent in _AGENT_SELF_INTENTS:
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        # Component/project questions are knowledge requests, not executable
        # operations. Route them through the evidence-backed chat path before
        # the generic executable-intent fallback below. Explicit file analysis
        # and test/run intents remain owned by Orchestrator.
        knowledge_type = QuestionClassifier.classify(user_question or text)
        knowledge_scope = resolve_project_scope(
            user_question or text,
            intent=intent,
        )
        knowledge_intents = {
            Intent.CYBER_EXPLAIN,
            Intent.ARCHITECTURE,
        }
        explicit_target = str((parsed or {}).get("target") or "").strip()
        if (
            intent in knowledge_intents
            and knowledge_scope == ProjectScope.CURRENT_PROJECT
            and knowledge_type in {"component", "relationship", "execution"}
            and not explicit_target
        ):
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        if (
            intent in (Intent.UNSUPPORTED, "unsupported")
            and parsed
            and parsed.get("semantic_pattern") == "DEVICE_MEMORY_UNSUPPORTED"
        ):
            return {
                "status": "unsupported",
                "intent": Intent.UNSUPPORTED,
                "text": (
                    "قراءة ذاكرة RAM للهاتف/الجهاز غير مدعومة من هذه البيئة. "
                    "فحص الصحة المتاح يقيس ذاكرة عملية الوكيل فقط، لا إجمالي "
                    "ذاكرة الجهاز أو المتاح منها."
                ),
                "mode": mode,
                "executed": False,
            }

        # Explicit operational modes.
        # SYSTEM commands are always routed to the orchestrator (agent actions).
        # Do NOT let TASK mode unconditionally override the intent decision —
        # intent remains authoritative to avoid hijacking conversational inputs.
        if mode == "SYSTEM":
            result = self.orchestrator.handle(
                text,
                parsed=parsed,
                context_resolved=True,
                conversation_history=chat_history,
                context_transition=context_transition,
            )
            result = dict(result)
            result["executed"] = result.get("status") != "needs_clarification"
            return result

        # ----------------------------------------------------
        # Unsupported is a canonical non-executable result.
        # Preserve the parser decision instead of letting the
        # conversational fallback relabel it as the current mode.
        if mode == "TASK" and intent in (Intent.UNSUPPORTED, "unsupported"):
            return {
                "status": "unsupported",
                "intent": intent,
                "text": f"لم أفهم الأمر: {text[:50]}",
                "mode": mode,
                "executed": False,
            }

        # ----------------------------------------------------
        # FOLLOW_UP MUST NOT automatically become CHAT.
        #
        # Example:
        # "كيف يعمل؟"
        #   mode   = FOLLOW_UP
        #   intent = cyber_explain
        #
        # Therefore -> Orchestrator.
        # ----------------------------------------------------
        # A generic request for suggestions without a subject is not yet
        # an executable project proposal. Let the conversational layer clarify
        # the domain instead of treating a broad NLU label as an actionable task.
        if (
            intent in {Intent.PROPOSE_SOLUTION, Intent.PLAN}
            and not explicit_target
            and str((parsed or {}).get("conversation_domain") or "general")
            not in {"technical", "project", "system"}
        ):
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        if intent not in _NON_EXECUTABLE_INTENTS:
            result = self.orchestrator.handle(
                text,
                parsed=parsed,
                context_resolved=True,
                conversation_history=chat_history,
                context_transition=context_transition,
            )
            result = dict(result)
            result["executed"] = result.get("status") != "needs_clarification"
            return result

        # Only genuinely unresolved conversational input reaches LLM.
        return self._handle_chat(
            text,
            mode,
            parsed=parsed,
            user_question=user_question or text,
            history=chat_history,
        )

    def _safe_parse(self, text: str, *, context_entity: dict | None = None) -> dict:
        try:
            if context_entity:
                result = parse(text, context_entity=context_entity)
            else:
                result = parse(text)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _normalize_transition_text(text: str) -> str:
        return " ".join(
            str(text or "").casefold()
            .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ئ", "ي").replace("ؤ", "و")
            .replace("ـ", "")
            .split()
        )

    @classmethod
    def _is_explicit_topic_switch(cls, text: str) -> bool:
        # Only direct switch/change wording qualifies; the existence of an
        # active topic or a generic "independent" marker is not enough.
        normalized = cls._normalize_transition_text(text)
        return any(marker in normalized for marker in (
            "لنغير الموضوع", "نغير الموضوع", "غير الموضوع",
            "ننتقل الى موضوع", "لننتقل الى موضوع",
            "لنغير المجال", "نغير المجال",
            "let's change the subject", "change the topic",
        ))

    @classmethod
    def _is_explicit_independent_topic(cls, text: str, parsed: dict) -> bool:
        # An independent-topic marker is authoritative even when target parsing
        # fails; requiring a target can leak the previous branch into the new
        # prompt and cause the privacy gate to reject unrelated content.
        normalized = cls._normalize_transition_text(text)
        return any(marker in normalized for marker in (
            "مستقل", "موضوع جديد", "موضوعا جديدا", "موضوعًا جديدًا",
            "موضوع اخر", "مجال اخر", "موضوع مختلف", "نقاش مختلف", "شيء اخر",
            "independent topic", "new topic", "another field", "different topic",
        ))

    def _resolve_generic_topic_reference(self, text: str) -> str | None:
        """Resolve ordinal/previous topic references without task-history fallback."""
        normalized = str(text or "").casefold()
        if not any(marker in normalized for marker in (
            "موضوع", "topic", "ارجع", "عد إلى", "عد الى", "حوار", "محادث",
            "نقاش", "حديث", "نرجع", "قبل هذا الموضوع",
        )):
            return None
        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        history = getattr(state, "history", []) if state is not None else []
        topics = []
        for turn in history or []:
            if not isinstance(turn, dict) or turn.get("role") != "user":
                continue
            target = str(turn.get("target") or "").strip()
            intent = str(getattr(turn.get("intent"), "value", turn.get("intent")) or "").casefold()
            if (
                target
                and intent in {
                    "cyber_explain", "explain", "question", "personal_chat",
                    "discussion", "chat",
                }
                and target not in topics
            ):
                topics.append(target)
        if not topics:
            return None
        if any(marker in normalized for marker in ("الأول", "الاول", "first")):
            return topics[0]
        if any(marker in normalized for marker in ("الثاني", "الثانى", "second")) and len(topics) > 1:
            return topics[1]
        if any(marker in normalized for marker in (
            "السابق", "السابقه", "السابقَ", "previous", "الاصلي", "الأصلي",
            "الرئيسي", "الرئيسيه", "موضوعنا", "حوارنا", "نقاشنا",
        )) or any(marker in normalized for marker in ("ارجع", "نرجع", "عد إلى", "عد الى")):
            state = getattr(self.dialogue_memory, "state", None)
            last_turn = next(
                (
                    item for item in reversed(getattr(state, "history", []) or [])
                    if isinstance(item, dict) and item.get("role") == "user"
                ),
                {},
            ) if state is not None else {}
            last_content = str(last_turn.get("content", "")).casefold() if isinstance(last_turn, dict) else ""
            if (
                isinstance(last_turn, dict)
                and (
                    last_turn.get("conversation_act") == "TOPIC_RETURN"
                    or any(marker in last_content for marker in ("ارجع", "نرجع", "عد إلى", "عد الى"))
                )
            ):
                previous = self.dialogue_memory.active_context_entity()
            else:
                get_previous = getattr(self.dialogue_memory, "previous_context_entity", None)
                previous = get_previous() if callable(get_previous) else None
            if isinstance(previous, dict) and previous.get("entity"):
                return str(previous["entity"]).strip()
            active = getattr(self.dialogue_memory, "last_topic", None)
            return str(active).strip() if active else topics[-1]
        return None

    @staticmethod
    def _dialogue_recall_requested(text: str, parsed: dict | None = None) -> bool:
        """Recognize requests to retrieve past dialogue, not discussion of recall itself."""
        normalized = ConversationManager._normalize_transition_text(text)
        if any(marker in normalized for marker in (
            "سياق العمل", "اخر جلسه", "المهام", "ملف العمل",
        )):
            return False

        # Meta-discussion about implementing or repairing the recall feature
        # must never be treated as a request to recall a previous conversation.
        discusses_feature = any(marker in normalized for marker in (
            "نطور", "تطوير", "يطور", "تطويره", "تحسين", "نحسن",
            "تصحيح", "نصحح", "اصلاح", "نصلح", "بناء", "نبني",
            "تصميم", "نصمم", "فحص", "نفحص", "تحليل", "نحلل",
            "اختبار", "نختبر", "مسار", "طبقات",
        ))
        feature_subject = any(marker in normalized for marker in (
            "سياق الحوار", "سياق المحادث", "استرجاع الحوار",
            "استرجاع المحادث", "طبقات الذاكره", "طبقات الذاكرة",
            "مسار الحوار", "مسارات الحوار",
        ))
        if discusses_feature and feature_subject:
            return False

        conversation_act = str(
            (parsed or {}).get("conversation_act") or ""
        ).upper()
        if conversation_act == "CONVERSATION_HISTORY_QUERY":
            return True

        # Strong retrieval/retrospection cues are sufficient on their own.
        # "سياق الحوار" by itself is not: users may be discussing how to improve
        # dialogue-context handling in the agent, not asking to retrieve a chat.
        strong_recall_markers = (
            "استرجع الحوار", "استرجاع الحوار", "استرجع المحادث", "استرجاع المحادث",
            "ماذا كنا نقول", "ماذا كنا نتحدث", "قبل هذا الموضوع",
            "الموضوع السابق", "الحوار السابق", "النقاش السابق", "الحديث السابق",
            "موضوعنا الاصلي", "ارجع الى الموضوع", "ارجع للحوار", "ارجع الى الحوار",
            "ارجع للنقاش", "ارجع الى النقاش", "اين توقفنا", "ما اخر موضوع",
            "ما اخر نقاش", "ما اخر حوار", "لخص الحوار", "ملخص الحوار",
        )
        if any(marker in normalized for marker in strong_recall_markers):
            return True

        # A generic mention of dialogue context becomes retrieval only when it
        # is paired with an explicit memory operation or a retrospective question.
        mentions_dialogue_context = any(marker in normalized for marker in (
            "سياق الحوار", "سياق المحادث", "سياق النقاش",
        ))
        asks_to_retrieve = any(marker in normalized for marker in (
            "استرجع", "استرجاع", "استعادة", "تذكر", "ماذا كنا", "ما كنا",
            "اين كنا", "لخص", "ملخص", "راجع ما",
        ))
        return mentions_dialogue_context and asks_to_retrieve

    def _ambiguous_resume_without_domain(self, text: str, parsed: dict) -> bool:
        normalized = str(text or "").casefold().strip()
        # A classified conversational continuation/history request is not a
        # work-session resume, even when the active dialogue has no named entity.
        conversation_act = str((parsed or {}).get("conversation_act") or "").upper()
        if conversation_act in {
            "CONVERSATION_CONTINUATION",
            "CONVERSATION_HISTORY_QUERY",
            "TOPIC_RETURN",
        }:
            return False
        resume_intents = {Intent.RESUME, Intent.SESSION_RESTORE, "resume", "session_restore"}
        intent = getattr(parsed.get("intent"), "value", parsed.get("intent"))
        if intent not in resume_intents and not any(marker in normalized for marker in (
            "اكمل", "أكمل", "استكمل", "نكمل",
        )):
            return False
        if any(marker in normalized for marker in (
            "العمل", "الملف", "المهمة", "جلسة", "مشروع", "work", "file", "task",
        )):
            return False
        active = (
            self.dialogue_memory.active_context_entity()
            if self.dialogue_memory and hasattr(self.dialogue_memory, "active_context_entity")
            else None
        )
        return not bool(active)

    def _context_kind(self, text: str, parsed: dict, transition) -> str:
        normalized = str(text or "").casefold()
        if str((parsed or {}).get("conversation_act") or "").upper() in {
            "CONVERSATION_CONTINUATION", "CONVERSATION_HISTORY_QUERY", "TOPIC_RETURN",
        }:
            return "dialogue"
        if self._ambiguous_resume_without_domain(text, parsed):
            return "unknown"
        if self._dialogue_recall_requested(text) or transition.value in CONTEXTUAL_TRANSITIONS:
            return "dialogue"
        if parsed.get("intent") in _AGENT_SELF_INTENTS:
            return "dialogue"
        if parsed.get("intent") == Intent.PERSONAL_CHAT or is_social_act(
            parsed.get("conversation_act")
        ):
            return "social"
        if any(marker in normalized for marker in (
            "اهلا", "أهلا", "مرحبا", "كيفك", "كيف الحال", "ماهو الحال",
        )):
            return "social"
        intent_value = str(
            getattr(parsed.get("intent"), "value", parsed.get("intent")) or ""
        ).casefold()
        explicit_work_intents = {
            "work_context", "work_status", "remaining_tasks", "remaining_work",
            "progress_report", "next_task", "project_report", "context_report",
            "last_project", "current_version", "show_changes",
        }
        if intent_value in explicit_work_intents:
            return "work"
        # An explicit request to continue the work in a named file is a work
        # continuation, not merely a question about project scope. Keep this
        # narrower than generic mentions of a file or repository.
        work_continuation_markers = (
            "استكمل العمل", "اكمل العمل", "أكمل العمل",
            "متابعة العمل", "تابع العمل", "واصل العمل",
        )
        if any(marker in normalized for marker in work_continuation_markers):
            return "work"
        scope = resolve_project_scope(text, intent=parsed.get("intent"))
        if scope == ProjectScope.CURRENT_PROJECT:
            return "project"
        return "unknown"

    @staticmethod
    def _local_social_answer(text: str, parsed: dict) -> dict | None:
        normalized = str(text or "").casefold()
        bare_confirmation = normalized.strip(" .!؟?")
        if (
            bare_confirmation in {"نعم", "أجل", "اجل", "بلى", "لا", "كلا", "yes", "no"}
            and (parsed or {}).get("source") == "bare_confirmation"
        ):
            reply = (
                "حسنًا."
                if bare_confirmation in {"لا", "كلا", "no"}
                else "حسنًا، أخبرني بما تريد متابعته."
            )
            return {
                "status": "success",
                "intent": Intent.PERSONAL_CHAT,
                "text": reply,
                "mode": "CHAT",
                "source": "local_social",
                "executed": False,
            }
        if any(marker in normalized for marker in (
            "اكمل", "أكمل", "استكمل", "نكمل", "ارجع", "استرجع",
        )):
            return None
        suggestion_markers = (
            "اقترح انت بعض المواضيع المثيرة", "اقترح أنت بعض المواضيع المثيرة",
            "اقترح انت بعض المواضيع", "اقترح أنت بعض المواضيع",
            "اقترح لي بعض المواضيع", "اقترح بعض المواضيع", "اقترح مواضيع",
            "مواضيع مثيرة للنقاش", "مواضيع للنقاش", "موضوع للنقاش",
            "انت اعطيني اقتراحات", "أنت أعطني اقتراحات", "اعطيني اقتراحات",
            "اعطني اقتراحات", "اقترح موضوع", "اقترح شي موضوع", "اقترح موضوعا",
            "انت اقترح شي موضوع", "نت قتارح شي موضوع", "عن اي موضوع قتارح نتا",
            "عن اي موضوع تقترح انت", "اقترحات اخرى", "اقتراحات اخرى", "اقتراحات أخرى",
            "اقتراحات اخرى في مجال اخر", "اقتراحات أخرى في مجال آخر",
            "اريد اقتراحات اخرى في مجال اخر", "أريد اقتراحات أخرى في مجال آخر",
            "موضوع الذي نتحدث فيه",
        )
        if any(marker in normalized for marker in suggestion_markers):
            return {
                "status": "success",
                "intent": Intent.PERSONAL_CHAT,
                "text": (
                    "ها بعض المواضيع المثيرة للنقاش:\n"
                    "1. واش الراحة كتجي من تحقيق الأهداف ولا من الاستمتاع بالطريق؟\n"
                    "2. واش التكنولوجيا كتزيد إبداع الإنسان ولا كتخليه يعتمد عليها؟\n"
                    "3. واش الفن يقدر يوصل أفكار ما تقدرش الكلمات توصلها؟ "
                    "اختار واحد ونكملو فيه. شنو رأيك؟"
                ),
                "mode": "CHAT",
                "source": "local_social",
                "executed": False,
            }
        social_markers = (
            "كيفك", "كيف الحال", "ماهو الحال", "حوار ودي", "حوار عادي",
            "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
            "نريد أن نتحدث فقط", "نريد ان نتحدث فقط", "دردشة فقط",
            "بغيت نهضر معاك", "بغيت نهضر", "موضوع خفيف", "كيفاش داز نهارك",
            "كيف داز نهارك", "كيف كان نهارك", "كيف قضيت يومك", "خلينا نهضرو",
            "نهدرو شوية", "نهضر معاك شوية",
        )
        if not any(marker in normalized for marker in social_markers):
            return None
        if any(marker in normalized for marker in ("كيفك", "كيف الحال", "ماهو الحال")):
            reply = "أنا بخير، شكرًا لسؤالك. كيف حالك أنت؟"
        elif any(marker in normalized for marker in ("كيفاش داز نهارك", "كيف داز نهارك")):
            reply = "نهاري هادئ، وأنا هنا للدردشة معك. ونتا كيف داز نهارك؟"
        elif "كيف كان نهارك" in normalized or "كيف قضيت يومك" in normalized:
            reply = "كان يومي هادئًا، وأنا جاهز للدردشة. كيف كان يومك أنت؟"
        elif any(marker in normalized for marker in (
            "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
            "نريد أن نتحدث فقط", "نريد ان نتحدث فقط", "دردشة فقط",
        )):
            reply = "حسنًا، لنتحدث بشكل ودي بعيدًا عن العمل والمهام. ما الذي يشغل بالك؟"
        else:
            reply = "أكيد، نهضرو على شي موضوع خفيف. شنو بغيتي تحكي ليا؟"
        return {
            "status": "success",
            "intent": Intent.PERSONAL_CHAT,
            "text": reply,
            "mode": "CHAT",
            "source": "local_social",
            "executed": False,
        }

    def _conversation_history_answer(self, text: str, parsed: dict | None = None) -> dict | None:
        """Answer recent-dialogue questions from bounded dialogue memory only."""
        normalized = str(text or "").casefold()
        history_act = str((parsed or {}).get("conversation_act") or "").upper()
        direct_suggestion = any(marker in normalized for marker in (
            "اقترح انت", "اقترح أنت", "اقترح لي", "اقترح بعض", "اقترح مواضيع",
            "اريد اقتراحات", "أريد اقتراحات", "اعطيني اقتراحات", "اعطني اقتراحات",
            "اقتراحات اخرى", "اقتراحات أخرى", "اقترحات اخرى",
        ))
        historical_recall = any(marker in normalized for marker in (
            "السابق", "سابقا", "سابقًا", "قبل", "تتذكر", "التي قدمتها",
            "التي اقترحتها", "ماذا اقترحت", "ما اقترحت",
        ))
        if direct_suggestion and not historical_recall:
            return None
        recovery_mode = str(
            ((parsed or {}).get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        # An unnamed return is a routing instruction, not a request to print
        # the archive. Let the transition resolver select the interrupted
        # branch and pass that branch to the response path.
        if recovery_mode == "interrupted_branch":
            return None
        if history_act == "TOPIC_RETURN" and str((parsed or {}).get("target") or "").strip():
            return None
        if history_act not in {"CONVERSATION_HISTORY_QUERY", "TOPIC_RETURN"} and any(marker in normalized for marker in (
            "ارجع", "عد إلى", "عد الى", "الاول", "الأول", "الثاني", "السابق",
            "previous", "first", "second",
        )):
            return None
        markers = (
            "موضوعين", "الموضوعين", "موضوعات", "المواضيع", "آخر موضوع",
            "اخر موضوع", "ماذا شرح", "ماذا شرحت", "شرحنا", "تكلمنا",
            "ناقشنا", "سجل المحادث", "تاريخ المحادث",
        )
        if history_act not in {"CONVERSATION_HISTORY_QUERY", "TOPIC_RETURN"} and not any(marker in normalized for marker in markers):
            return None
        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        current_session_id = str(getattr(state, "session_id", "") or "")
        history = [
            turn for turn in (getattr(state, "history", []) if state is not None else [])
            if isinstance(turn, dict)
            and (
                not current_session_id
                or str(turn.get("session_id") or "") == current_session_id
            )
        ]
        exchanges = getattr(state, "exchange_archive", []) if state is not None else []
        exchanges = [
            item for item in (exchanges or [])
            if isinstance(item, dict)
            and (
                not current_session_id
                or (
                    not str(item.get("session_id") or "").strip()
                    and item.get("context_kind") == "execution"
                )
                or str(item.get("session_id") or "") == current_session_id
            )
        ]
        response_mode = str(
            ((parsed or {}).get("response_attributes") or {}).get(
                "dialogue_response_mode", ""
            )
        ).casefold()
        if response_mode in {"summary", "last_question", "answer", "transcript"}:
            return self._answer_dialogue_history(text, response_mode, exchanges)
        topics = []
        for turn in history or []:
            if not isinstance(turn, dict) or turn.get("role") != "user":
                continue
            target = str(turn.get("target") or "").strip()
            intent = str(turn.get("intent") or "").casefold()
            if not target or intent not in {"cyber_explain", "explain", "question"}:
                continue
            if target not in topics:
                topics.append(target)
        if not topics:
            dialogue_exchanges = self._latest_dialogue_branch([
                item for item in exchanges
                if isinstance(item, dict)
                and item.get("context_kind") not in {"work", "system"}
                and item.get("conversation_domain") not in {"work", "system"}
                and (
                    not current_session_id
                    or str(item.get("session_id") or "") == current_session_id
                )
            ])[-6:]
            if dialogue_exchanges:
                return {
                    "status": "success", "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": "في الحوار السابق دار التبادل التالي:\n"
                    + "\n".join(self._format_dialogue_exchanges(dialogue_exchanges)),
                    "dialogue_turns": dialogue_exchanges,
                    "executed": False,
                }
            if history_act == "TOPIC_RETURN":
                return {
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": (
                        "لا يوجد موضوع سابق مسجل أستطيع الرجوع إليه في هذه الجلسة. "
                        "اذكر الموضوع الذي تريد استعادته."
                    ),
                    "executed": False,
                }
            return {
                "status": "success", "intent": Intent.MEMORY_DUMP,
                "source": "dialogue_memory",
                "text": "لا توجد موضوعات تعليمية مسجلة في الحوار الحالي.",
                "executed": False,
            }
        text = "الموضوعات التي نوقشت بالترتيب: " + "، ".join(topics)
        if history_act == "CONVERSATION_HISTORY_QUERY" and exchanges:
            # Select complete archived exchanges, not individual turns. Keep
            # relevant dialogue while excluding only explicit work context.
            selected = [
                item for item in exchanges
                if item.get("context_kind") != "work"
                and item.get("conversation_domain") != "work"
                and (
                    not item.get("target")
                    or item.get("target") in topics
                    or any(str(topic).casefold() in str(item.get("user", "")).casefold() for topic in topics)
                )
            ][-6:]
            text += "\n\nالتبادل الأخير:\n" + "\n".join(
                self._format_dialogue_exchanges(selected)
            )
        return {
            "status": "success", "intent": Intent.MEMORY_DUMP,
            "source": "dialogue_memory",
            "text": text,
            "topics": topics,
            "executed": False,
        }

    @staticmethod
    def _latest_dialogue_branch(exchanges: list[dict]) -> list[dict]:
        """Select the last substantive dialogue branch, ignoring recall/save commands."""
        valid = [item for item in (exchanges or []) if isinstance(item, dict)]

        def user_text(item: dict) -> str:
            return str(item.get("user") or "").casefold().replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

        def is_control_exchange(item: dict) -> bool:
            user = " ".join(user_text(item).split())
            transition = str(item.get("context_transition") or "").casefold()
            kind = str(item.get("context_kind") or "").casefold()
            domain = str(item.get("conversation_domain") or "").casefold()
            if kind in {"work", "system", "execution"} or domain in {"work", "system", "execution"}:
                return True
            if user == "حفظ" or user.startswith("حفظ "):
                return True
            controls = (
                "استرجع النقاش الذي انقطع",
                "استرجاع الحوار",
                "استرجع الحوار",
                "ماذا كنا نقول",
                "ماذا كنا نتحدث",
                "استكمال الحوار",
                "استكمال النقاش",
                "استرجاتع الجلسة السابقة",
                "استرجاع الجلسة السابقة",
            )
            return any(marker in user for marker in controls)

        def inferred_boundary(item: dict) -> str:
            transition = str(item.get("context_transition") or "").casefold()
            if transition in {"new_independent", "explicit_switch", "restore"}:
                return transition
            user = " ".join(user_text(item).split())
            if any(marker in user for marker in (
                "لنغير الموضوع", "نغير الموضوع", "غير الموضوع",
                "لنغير المجال", "نغير المجال", "ننتقل الى موضوع",
                "لننتقل الى موضوع", "change the topic", "change the subject",
            )):
                return "explicit_switch"
            if any(marker in user for marker in (
                "نرجع الى موضوع", "نعود الى موضوع", "العودة الى موضوع",
                "ارجع الى موضوع", "نرجع لموضوع", "نعود لموضوع",
                "back to", "return to",
            )):
                return "restore"
            return ""

        substantive = [item for item in valid if not is_control_exchange(item)]
        if not substantive:
            return []

        # A restored topic is a new active branch even when older archives recorded
        # its transition as ambiguous. Ignore later recall/save commands so they
        # cannot replace that branch as the apparent "latest topic".
        for index in range(len(substantive) - 1, -1, -1):
            if inferred_boundary(substantive[index]):
                return substantive[index:]

        # Legacy archives without transition markers: use the most recent
        # contiguous dialogue segment rather than claiming the whole archive.
        return substantive[-1:]

    def _answer_dialogue_history(
        self,
        text: str,
        response_mode: str,
        exchanges: list[dict],
    ) -> dict:
        """Answer a dialogue-history request without routing it as project work."""
        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        current_session_id = str(getattr(state, "session_id", "") or "")
        relevant = [
            item for item in exchanges
            if item.get("context_kind") != "work"
            and item.get("conversation_domain") != "work"
            and (
                not current_session_id
                or (
                    not str(item.get("session_id") or "").strip()
                    and item.get("context_kind") == "execution"
                )
                or str(item.get("session_id") or "") == current_session_id
            )
        ][-8:]

        base = {
            "status": "success",
            "intent": Intent.MEMORY_DUMP,
            "source": "dialogue_memory",
            "executed": False,
            "dialogue_response_mode": response_mode,
        }
        if response_mode == "last_question":
            question_starts = (
                "هل ", "ما ", "ماذا ", "كيف ", "لماذا ", "من ", "أين ",
                "اين ", "متى ", "كم ", "أي ", "اي ", "ماهو ", "ما هي ",
            )
            last_question = next(
                (
                    str(item.get("user") or "").strip()
                    for item in reversed(relevant)
                    if str(item.get("user") or "").strip()
                    and (
                        "؟" in str(item.get("user") or "")
                        or "?" in str(item.get("user") or "")
                        or str(item.get("user") or "").strip().casefold().startswith(question_starts)
                    )
                ),
                "",
            )
            if not last_question:
                return {
                    **base,
                    "status": "needs_clarification",
                    "text": "لا أجد سؤالًا صريحًا في سجل الحوار القريب؛ لن أستبدله برسالة عادية.",
                }
            return {
                **base,
                "text": f"آخر سؤال طرحته عليّ كان: «{last_question}».",
                "last_user_message": last_question,
            }

        if not relevant:
            return {
                **base,
                "status": "needs_clarification",
                "text": "لا يوجد سجل حوار كافٍ للإجابة عن هذا الطلب.",
            }

        if response_mode == "transcript":
            return {
                **base,
                "text": "نص الحوار المسجل:\n"
                + "\n".join(self._format_dialogue_exchanges(relevant)),
                "dialogue_turns": relevant,
            }

        archive = []
        for item in relevant:
            archive.append(
                "المستخدم: " + str(item.get("user") or "").strip()
                + "\nالوكيل: " + str(item.get("assistant") or "").strip()
            )
        # History recall is a provenance-sensitive operation: do not ask an
        # unconstrained language model to reconstruct events from a transcript.
        # Render only the exact bounded exchanges present in DialogueMemory.
        if response_mode == "answer":
            query = str(text or "").casefold()
            matched = [
                item for item in relevant
                if any(
                    token and len(token) > 2
                    and token in " ".join((
                        str(item.get("target") or ""),
                        str(item.get("user") or ""),
                        str(item.get("assistant") or ""),
                    )).casefold()
                    for token in query.split()
                )
            ]
            selected = matched[-3:]
            if not selected:
                return {
                    **base,
                    "status": "needs_clarification",
                    "text": "لا أجد في سجل الحوار المحفوظ تفاصيل موثوقة عن هذا الموضوع؛ لن أخمّن.",
                }
            return {
                **base,
                "text": "بحسب سجل الحوار المحفوظ:\n"
                + "\n".join(self._format_dialogue_exchanges(selected)),
                "dialogue_turns": selected,
            }

        if response_mode == "summary":
            # Requests explicitly asking what was said in previous replies need
            # the recent recorded exchanges, not only the active branch. The
            # branch-only view remains appropriate for a plain current-state
            # summary, where mixing independent topics would be misleading.
            normalized_query = str(text or "").casefold()
            recall_recent_exchanges = any(marker in normalized_query for marker in (
                "الردود السابقة", "الردود السابقه", "قبل قليل",
                "ماذا كنا نقول", "ماذا قلنا", "ما كنا نقول",
            ))
            branch = (
                relevant[-5:]
                if recall_recent_exchanges
                else self._latest_dialogue_branch(relevant)[-5:]
            )
            if recall_recent_exchanges:
                lines = []
                for item in branch:
                    user = " ".join(str(item.get("user") or "").split())
                    assistant = " ".join(str(item.get("assistant") or "").split())
                    if not user and not assistant:
                        continue
                    # Compact each exchange into its subject and recorded
                    # takeaway; do not render a role-labelled transcript.
                    line = f"- ناقشنا: {user[:130]}"
                    if assistant:
                        takeaway = assistant.split("。", 1)[0].split(". ", 1)[0].strip()
                        if len(takeaway) > 160:
                            takeaway = takeaway[:157].rstrip() + "..."
                        line += f"؛ الخلاصة المسجلة: {takeaway}"
                    lines.append(line)
                return {
                    **base,
                    "text": "ملخص موثّق للحوار المسجّل:\n" + "\n".join(lines),
                    "dialogue_turns": branch[-6:],
                }

            last = branch[-1] if branch else {}
            active_topic = str(
                getattr(state, "last_topic", None)
                or last.get("target")
                or ""
            ).strip()
            summary_lines = []
            if active_topic:
                summary_lines.append(f"- الموضوع النشط: {active_topic}")
            else:
                summary_lines.append("- الموضوع النشط: حوار عام؛ لم يُسجّل له عنوان مستقل.")
            user = " ".join(str(last.get("user") or "").split())
            assistant = " ".join(str(last.get("assistant") or "").split())
            if user:
                excerpt = user[:180] + ("…" if len(user) > 180 else "")
                summary_lines.append(f"- آخر رسالة واردة: {excerpt}")
            if assistant:
                excerpt = assistant[:220] + ("…" if len(assistant) > 220 else "")
                summary_lines.append(f"- نقطة التوقف: {excerpt}")
            return {
                **base,
                "text": "ملخص الحوار الحالي:\n" + "\n".join(summary_lines),
                "dialogue_turns": branch,
            }

        task = (
            "أجب عن طلب المستخدم الحالي بالاعتماد حصريًا على سجل الحوار المرفق.\n"
            "لا تضف أحداثًا غير موجودة.\n\n"
            f"طلب المستخدم الحالي: {text}\n\n"
            "سجل الحوار السابق:\n" + "\n\n".join(archive)
        )
        try:
            generated = gateway_ask(
                task,
                system=(
                    "أنت تسترجع حوارًا سابقًا. التزم بالسجل فقط. "
                    "لا تضف أحداثًا غير موجودة. أجب مباشرة وبالعربية."
                ),
                max_tokens=900,
                temperature=0.2,
                routing_text=text,
            )
            answer = str((generated or {}).get("text") or "").strip()
            if (generated or {}).get("status") == "success" and answer:
                return {**base, "text": answer}
        except Exception:
            pass

        # Offline/provider-failure fallback: compact and explicitly bounded,
        # not a full transcript and not a fabricated semantic interpretation.
        if response_mode == "summary":
            lines = []
            seen = set()
            for item in relevant[-5:]:
                user_turn = " ".join(str(item.get("user") or "").split())
                if not user_turn or user_turn.casefold() in seen:
                    continue
                seen.add(user_turn.casefold())
                assistant_turn = " ".join(str(item.get("assistant") or "").split())
                line = f"- طلب المستخدم: {user_turn[:110]}"
                if assistant_turn:
                    first_sentence = assistant_turn.split("。", 1)[0].split(". ", 1)[0]
                    line += f"؛ رد الوكيل باختصار: {first_sentence[:110]}"
                lines.append(line)
            return {
                **base,
                "text": "ملخص موجز من سجل الحوار المتاح:\n" + "\n".join(lines),
                "summary_fallback": True,
            }
        return {
            **base,
            "status": "needs_clarification",
            "text": "تعذر تحديد الإجابة من سجل الحوار المتاح دون تخمين.",
        }

    @staticmethod
    def _format_dialogue_exchanges(exchanges: list[dict]) -> list[str]:
        """Render bounded recall with explicit user/assistant roles."""
        lines = []
        for item in exchanges:
            user = str(item.get("user") or "").strip()
            assistant = str(item.get("assistant") or "").strip()
            if user:
                lines.append(f"- المستخدم: {user}")
            if assistant:
                lines.append(f"  الوكيل: {assistant[:1200]}")
        return lines

    def _classify_context_transition(
        self,
        mode: str,
        parsed: dict,
        *,
        text: str = "",
    ) -> ContextTransition:
        """Classify the current semantic subject against dialogue-owned state."""
        parsed = parsed or {}
        entity_type = str(parsed.get("entity_type", "")).upper()
        target = str(parsed.get("target") or "").strip()
        intent = getattr(parsed.get("intent"), "value", parsed.get("intent"))
        pattern = parsed.get("semantic_pattern")
        active_context = None
        if self.dialogue_memory:
            get_active_context = getattr(
                self.dialogue_memory,
                "active_context_entity",
                None,
            )
            if callable(get_active_context):
                active_context = get_active_context()
        active_topic = (
            active_context.get("entity")
            if isinstance(active_context, dict)
            else None
        )

        conversation_act = parsed.get("conversation_act")
        normalized_request = str(text or "").casefold()
        explicit_explain_markers = (
            "اشرح", "شرح", "وضح", "عرّف", "عرف", "ما هو", "ماهي",
            "حدثني عن", "دعنا نتحدث عن", "let's discuss", "explain",
        )
        explicit_resume_markers = (
            "اكمل", "أكمل", "استكمل", "تابع", "واصل", "من نقطة التوقف",
            "ارجع", "نرجع", "عد إلى", "عد الى", "continue", "resume",
        )
        starts_explicit_explanation = (
            target
            and any(marker in normalized_request for marker in explicit_explain_markers)
            and not any(marker in normalized_request for marker in explicit_resume_markers)
        )
        if (
            starts_explicit_explanation
            and active_topic
            and self._same_topic(target, active_topic)
            and conversation_act != "TOPIC_RETURN"
        ):
            # "Explain X in detail" starts a fresh answer even if a persisted
            # session happened to leave X as the active topic. Only explicit
            # continuation/return language may resume the old stopping point.
            return ContextTransition.EXPLICIT_SWITCH
        if parsed.get("semantic_pattern") == "GENERIC_TOPIC_REFERENCE":
            return (
                ContextTransition.RESTORE
                if conversation_act == "TOPIC_RETURN"
                else ContextTransition.REFERENCE
            )
        if intent in _AGENT_SELF_INTENTS:
            return ContextTransition.NEW_INDEPENDENT
        if conversation_act == "TOPIC_RETURN":
            # A named return must resolve that exact topic. Never fall back to
            # whichever branch happens to be last in context_history.
            if target and self.dialogue_memory:
                get_topic = getattr(self.dialogue_memory, "context_for_topic", None)
                named_context = get_topic(target) if callable(get_topic) else None
                if named_context:
                    return ContextTransition.RESTORE
                if active_topic and self._same_topic(target, active_topic):
                    return ContextTransition.CONTINUE
                return ContextTransition.AMBIGUOUS
            get_previous = getattr(
                self.dialogue_memory,
                "previous_context_entity",
                None,
            ) if self.dialogue_memory else None
            return (
                ContextTransition.RESTORE
                if callable(get_previous) and get_previous()
                else ContextTransition.AMBIGUOUS
            )
        if conversation_act in {"CORRECTION", "COMPOUND_REFERENCE"}:
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )
        if conversation_act == "CONVERSATION_CONTINUATION":
            # A named, different subject is an explicit branch switch even if
            # a semantic marker such as "نقطة" made the utterance look like a
            # continuation. Prefer a matching archived branch when available.
            if target and active_topic and not self._same_topic(target, active_topic):
                get_topic = getattr(self.dialogue_memory, "context_for_topic", None) if self.dialogue_memory else None
                named_context = get_topic(target) if callable(get_topic) else None
                return (
                    ContextTransition.RESTORE
                    if named_context else ContextTransition.EXPLICIT_SWITCH
                )
            if target and not active_topic:
                return ContextTransition.NEW_INDEPENDENT
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )
        if is_style_act(conversation_act) and not target:
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )
        # A generic CASUAL_CONVERSATION fallback is weaker than a structural
        # reference/elaboration marker or an explicit FOLLOW_UP mode.
        if (
            is_social_act(conversation_act)
            and str(conversation_act).upper() != "CASUAL_CONVERSATION"
            and not target
        ):
            return ContextTransition.AMBIGUOUS

        if entity_type == "REFERENCE":
            return (
                ContextTransition.REFERENCE
                if active_topic else ContextTransition.AMBIGUOUS
            )

        if target:
            if active_topic and self._same_topic(target, active_topic):
                return ContextTransition.CONTINUE
            previous_context = None
            if self.dialogue_memory:
                get_context = getattr(
                    self.dialogue_memory,
                    "context_for_topic",
                    None,
                )
                if callable(get_context):
                    previous_context = get_context(target)
                pending_topic = getattr(
                    self.dialogue_memory,
                    "pending_topic",
                    None,
                )
            else:
                pending_topic = None
            valid_target = entity_type not in {
                "", "UNKNOWN", "REFERENCE", "ELABORATION",
            }
            if valid_target and (
                previous_context
                or self._same_topic(target, pending_topic)
            ):
                return ContextTransition.RESTORE
            return (
                ContextTransition.EXPLICIT_SWITCH
                if active_topic else ContextTransition.NEW_INDEPENDENT
            )

        if entity_type == "ELABORATION":
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )

        if pattern in {"CONTINUE_WORK", "GIVE_EXAMPLE"}:
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )

        if mode == "FOLLOW_UP":
            if not active_topic:
                return ContextTransition.AMBIGUOUS
            previous_intent = getattr(
                getattr(self.dialogue_memory, "state", None),
                "last_intent",
                None,
            )
            previous_intent = getattr(previous_intent, "value", previous_intent)
            return (
                ContextTransition.CONTINUE
                if intent and intent == previous_intent
                else ContextTransition.REFERENCE
            )

        if mode == "CHAT" and intent in _NON_EXECUTABLE_INTENTS:
            return ContextTransition.AMBIGUOUS

        incomplete = is_incomplete({
            "intent": intent or "",
            "target": "",
            "entity": {"value": ""},
        })
        if incomplete or not intent:
            return ContextTransition.AMBIGUOUS

        return ContextTransition.NEW_INDEPENDENT

    @staticmethod
    def _same_topic(left, right) -> bool:
        def normalize_topic(value):
            return " ".join(
                str(value).casefold().strip(" \t\r\n.,،؛:!?؟()[]{}\"'").split()
            )
        return normalize_topic(left) == normalize_topic(right)

    def _history_for_transition(
        self,
        transition: ContextTransition,
        parsed: dict,
    ) -> list:
        """Build bounded prompt history from durable dialogue exchanges.

        The visible turn list is intentionally short. Prefer the exchange archive
        when selecting a branch so recent relevant turns survive transcript rollover.
        Work/system exchanges are never admitted to a dialogue prompt.
        """
        if not self.dialogue_memory:
            return []

        state = getattr(self.dialogue_memory, "state", None)
        history = getattr(state, "history", []) if state is not None else []
        exchanges = getattr(state, "exchange_archive", []) if state is not None else []

        current_session_id = str(getattr(state, "session_id", "") or "")

        def allowed(item):
            if not isinstance(item, dict):
                return False
            kind = str(item.get("context_kind") or "").casefold()
            domain = str(item.get("conversation_domain") or "").casefold()
            item_session_id = str(item.get("session_id") or "")
            # Fail closed when a session ID is available: untagged legacy turns
            # cannot be proven to belong to this session.
            same_session = (
                not current_session_id
                or item_session_id == current_session_id
            )
            return (
                kind not in {"work", "system"}
                and domain not in {"work", "system"}
                and same_session
            )

        recovery_mode = str(
            ((parsed or {}).get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        if recovery_mode == "interrupted_branch":
            def is_recovery_request(item):
                user_text = str(item.get("user") or "").casefold()
                return (
                    "استرجع النقاش الذي انقطع" in user_text
                    or "استرجع الحوار الذي انقطع" in user_text
                    or "recover the interrupted discussion" in user_text
                )

            valid = [
                item for item in (exchanges or [])
                if allowed(item) and not is_recovery_request(item)
            ]

            def effective_transition(item):
                transition_value = str(
                    item.get("context_transition") or ""
                ).casefold()
                if transition_value in {"new_independent", "explicit_switch", "restore"}:
                    return transition_value
                user_text = str(item.get("user") or "")
                if self._is_explicit_topic_switch(user_text):
                    return "explicit_switch"
                if self._is_explicit_independent_topic(user_text, {}):
                    return "new_independent"
                normalized = user_text.casefold().replace("أ", "ا").replace("إ", "ا")
                if any(marker in normalized for marker in (
                    "نعود إلى", "نعود الى", "نرجع إلى", "نرجع الى",
                    "عدنا إلى", "عدنا الى", "العودة إلى", "العودة الى",
                    "لنعد إلى", "لنعد الى", "ارجع إلى", "ارجع الى",
                    "الرجوع إلى", "الرجوع الى", "عودة إلى", "عودة الى",
                    "back to ", "return to ",
                )):
                    return "restore"
                return transition_value

            boundaries = [
                (index, effective_transition(item))
                for index, item in enumerate(valid)
                if effective_transition(item) in {
                    "new_independent", "explicit_switch", "restore"
                }
            ]
            if boundaries:
                latest_boundary, latest_kind = boundaries[-1]
                if latest_kind == "restore":
                    # A later explicit return reactivates the earlier branch.
                    # Continue from that restored branch, not the intervening one.
                    selected = valid[latest_boundary:]
                elif len(boundaries) > 1:
                    previous_boundary = boundaries[-2][0]
                    selected = valid[previous_boundary:latest_boundary]
                elif latest_boundary > 0:
                    # A legacy archive may have one explicit boundary after
                    # untagged earlier exchanges; those exchanges are the best
                    # available candidate for the interrupted branch.
                    selected = valid[:latest_boundary]
                else:
                    # With only one known branch there is no older branch to
                    # distinguish. Fall back to that branch rather than return
                    # an empty history and trigger a clarification loop.
                    selected = valid[-4:]
            else:
                # Legacy archives may lack transition metadata. Prefer the last
                # few dialogue exchanges, excluding work and failed recovery turns.
                selected = valid[-4:]
            if selected:
                return self._exchange_history_turns(selected[-4:])[-8:]
            return []

        topic = None
        if transition in {ContextTransition.RESTORE, ContextTransition.EXPLICIT_SWITCH}:
            topic = (parsed or {}).get("target")
        elif transition.value in CONTEXTUAL_TRANSITIONS:
            active = self.dialogue_memory.active_context_entity()
            topic = active.get("entity") if isinstance(active, dict) else None

        if transition == ContextTransition.AMBIGUOUS and is_social_act(
            (parsed or {}).get("conversation_act")
        ):
            branch = self._latest_dialogue_branch([
                item for item in (exchanges or []) if allowed(item)
            ])
            selected = [item for item in branch if not item.get("target")][-8:]
            if selected:
                return self._exchange_history_turns(selected)[-8:]
            return [
                turn for turn in (history or [])
                if allowed(turn) and not turn.get("target")
            ][-8:]

        if transition == ContextTransition.AMBIGUOUS and str(
            (parsed or {}).get("conversation_act") or ""
        ).upper() == "CONVERSATION_CONTINUATION":
            selected = self._latest_dialogue_branch(
                [item for item in (exchanges or []) if allowed(item)]
            )[-8:]
            if selected:
                return self._exchange_history_turns(selected)[-8:]
            return [turn for turn in (history or []) if allowed(turn)][-8:]

        if not topic:
            # General conversation branches may not have a canonical entity.
            # For an authorized continuation/return, use recent dialogue exchanges
            # rather than dropping context solely because no entity was extracted.
            if transition in CONTEXTUAL_TRANSITIONS:
                selected = self._latest_dialogue_branch(
                    [item for item in (exchanges or []) if allowed(item)]
                )[-8:]
                if selected:
                    return self._exchange_history_turns(selected)[-8:]
                return [turn for turn in (history or []) if allowed(turn)][-8:]
            return []

        selected = [
            item for item in (exchanges or [])
            if allowed(item) and item.get("target")
            and self._same_topic(item.get("target"), topic)
        ][-8:]
        if selected:
            return self._exchange_history_turns(selected)[-8:]

        # Compatibility with checkpoints created before exchange archives.
        return [
            turn for turn in (history or [])
            if allowed(turn) and turn.get("target")
            and self._same_topic(turn.get("target"), topic)
        ][-8:]

    @staticmethod
    def _exchange_history_turns(exchanges: list[dict]) -> list[dict]:
        """Convert archived exchanges to the standard prompt-history shape."""
        turns = []
        for exchange in exchanges:
            if not isinstance(exchange, dict):
                continue
            shared = {
                "mode": exchange.get("mode"),
                "intent": exchange.get("intent"),
                "target": exchange.get("target"),
                "conversation_domain": exchange.get("conversation_domain", "general"),
                "conversation_act": exchange.get("conversation_act", "NONE"),
                "context_kind": exchange.get("context_kind", "unknown"),
            }
            user_text = str(exchange.get("user") or "").strip()
            assistant_text = str(exchange.get("assistant") or "").strip()
            if user_text:
                turns.append({"role": "user", "content": user_text, **shared})
            if assistant_text:
                turns.append({"role": "assistant", "content": assistant_text, **shared})
        return turns

    # Compatibility entry points
    # --------------------------------------------------------

    def _handle_task(self, text: str) -> dict:
        return self.process(text)

    def _handle_system(self, text: str) -> dict:
        return self.process(text)

    def _handle_follow_up(self, text: str) -> dict:
        return self.process(text)

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
            self_knowledge = (
                build_agent_self_knowledge(intent)
                if intent in _AGENT_SELF_INTENTS
                else None
            )
            project_scope = resolve_project_scope(
                user_question or text,
                intent=intent,
            )
            
            # Retrieve project knowledge for the question if applicable
            project_knowledge = None
            knowledge_type = QuestionClassifier.classify(user_question or text)
            if (
                user_question
                and (
                    intent in _AGENT_SELF_INTENTS
                    or knowledge_type in {"component", "relationship", "execution", "file"}
                )
                and project_scope == ProjectScope.CURRENT_PROJECT
            ):
                try:
                    project_knowledge = retrieve_for_question(user_question)
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
            
            system, prompt = build_chat_prompt(
                text,
                list(history or []),
                agent_self_knowledge=self_knowledge,
                project_knowledge=project_knowledge,
                project_scope=project_scope,
                conversation_semantics={
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

            result = gateway_ask(
                prompt,
                system=system,
                # Reasoning can consume the full budget before GPT-5 emits
                # visible text; grounded self-descriptions need extra headroom.
                max_tokens=4000 if self_knowledge else 1600,
                temperature=0.7,
                routing_text=text,
            )

            if result.get("status") != "success":
                raise RuntimeError(
                    result.get("message")
                )

            reply = result.get("text", "")

            if not reply:
                raise ValueError("empty")

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
            fallback = (
                "تعذر الوصول إلى نموذج الذكاء الاصطناعي حالياً. "
                "تحقق من الاتصال أو إعدادات المزود ثم أعد المحاولة."
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
                "gateway_error": (
                    result.get("error")
                    if isinstance(result, dict)
                    else None
                ),
                "error": str(e),
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
                result = dict(self.process(f"ارجع لشرح {topic}"))
                result.setdefault("topic", topic)
                return result

        return {
            "status": "success",
            "intent": "topic_restore",
            "text": "لا يوجد موضوع مؤجل.",
        }
