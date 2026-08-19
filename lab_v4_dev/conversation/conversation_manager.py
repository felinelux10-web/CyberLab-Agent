"""
Conversation Manager — Unified Conversation/Intent Routing.

Authority contract:

ModeDetector
    -> conversational shape only.

IntentParser
    -> canonical executable Intent resolver.

Context
    -> enriches references/targets only.

ConversationManager
    -> performs ONE Intent resolution and chooses ONE execution owner.

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
from lab_v4_dev.conversation.semantic_contract import build_semantic_request
from lab_v4_dev.llm.prompt_builder import build_chat_prompt
from lab_v4_dev.llm.gateway import ask as gateway_ask
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent


_NON_EXECUTABLE_INTENTS = {
    Intent.UNCLEAR,
    Intent.UNSUPPORTED,
    Intent.HELP,
    "unclear",
    "unsupported",
    "help",
}


class ConversationManager:

    def __init__(self, orchestrator, dialogue_memory=None, dni=None):
        self.orchestrator = orchestrator
        self.dialogue_memory = dialogue_memory
        self.dni = dni

    def process(self, user_input: str) -> dict:
        mode = detect_mode(user_input)

        # ----------------------------------------------------
        # ONE canonical Intent resolution.
        # ----------------------------------------------------
        resolved_input = user_input

        if mode == "FOLLOW_UP" and self.dialogue_memory:
            resolved_input = self.dialogue_memory.resolve_references(user_input)

        parsed = self._safe_parse(resolved_input)

        # ----------------------------------------------------
        # ONE execution owner.
        # ----------------------------------------------------
        result = self._dispatch(
            resolved_input,
            mode,
            parsed,
        )

        # ----------------------------------------------------
        # Semantic metadata only.
        # ----------------------------------------------------
        semantic = build_semantic_request(
            user_input,
            mode,
            confidence=(
                float(parsed.get("confidence", 0.0))
                if parsed else 0.0
            ),
            target=(
                parsed.get("target")
                if parsed else None
            ),
            requires_context=(mode == "FOLLOW_UP"),
        )

        result = dict(result)
        result["semantic_request"] = semantic.as_dict()

        # ----------------------------------------------------
        # Presentation layer only.
        # ----------------------------------------------------
        if result.get("text"):
            result["text"] = single_question(
                format_response(result["text"], mode)
            )

        if self.dni:
            self.dni.set_conversation_analysis({
                "intent": result.get("intent"),
                "mode": result.get("mode", mode),
                "confidence": (
                    parsed.get("confidence", 0.0)
                    if parsed else 0.0
                ),
            })

        # DialogueMemory.update() remains exclusively in Agent.run().
        return result

    def _dispatch(self, text: str, mode: str, parsed: dict) -> dict:
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

        # Explicit operational modes.
        if mode in ("TASK", "SYSTEM"):
            return self.orchestrator.handle(
                text,
                parsed=parsed,
            )

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
        if intent not in _NON_EXECUTABLE_INTENTS:
            return self.orchestrator.handle(
                text,
                parsed=parsed,
            )

        # Only genuinely unresolved conversational input reaches LLM.
        return self._handle_chat(text, mode)

    def _safe_parse(self, text: str) -> dict:
        try:
            result = parse(text)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    # --------------------------------------------------------
    # Compatibility entry points
    # --------------------------------------------------------

    def _handle_task(self, text: str) -> dict:
        parsed = self._safe_parse(text)
        return self.orchestrator.handle(text, parsed=parsed)

    def _handle_system(self, text: str) -> dict:
        parsed = self._safe_parse(text)
        return self.orchestrator.handle(text, parsed=parsed)

    def _handle_follow_up(self, text: str) -> dict:
        resolved = text

        if self.dialogue_memory:
            resolved = self.dialogue_memory.resolve_references(text)

        parsed = self._safe_parse(resolved)

        if parsed.get("intent") not in _NON_EXECUTABLE_INTENTS:
            return self.orchestrator.handle(
                resolved,
                parsed=parsed,
            )

        return self._handle_chat(resolved, "DISCUSSION")

    def _handle_chat(self, text: str, mode: str) -> dict:
        result = {}

        try:
            history = (
                getattr(
                    self.dialogue_memory,
                    "last_list",
                    [],
                )
                if self.dialogue_memory
                else []
            )

            system, prompt = build_chat_prompt(
                text,
                history,
            )

            result = gateway_ask(
                prompt,
                system=system,
                max_tokens=300,
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
                "intent": mode.lower(),
                "text": reply,
                "mode": mode,
                "source": "llm",
                "provider_used": result.get("provider_used"),
                "provider_chain": result.get(
                    "provider_chain",
                    [],
                ),
                "model": result.get("model"),
            }

        except Exception as e:
            fallback = (
                "تعذر الوصول إلى نموذج الذكاء الاصطناعي حالياً. "
                "تحقق من الاتصال أو إعدادات المزود ثم أعد المحاولة."
            )

            return {
                "status": "error",
                "intent": mode.lower(),
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
            topic = (
                self.dialogue_memory.restore_pending()
            )

            if topic:
                return {
                    "status": "success",
                    "intent": "topic_restore",
                    "text": (
                        f"نرجع للموضوع السابق: {topic}"
                    ),
                    "topic": topic,
                }

        return {
            "status": "success",
            "intent": "topic_restore",
            "text": "لا يوجد موضوع مؤجل.",
        }
