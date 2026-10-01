"""
P05 — Dialogue Memory.

Owns dialogue state and reference resolution.
Does not route, execute, call providers, or decide intent.
"""

from __future__ import annotations

from lab_v4_dev.conversation.dialogue_contract import DialogueState
from lab_v4_dev.conversation.semantic_contract import CONTEXTUAL_TRANSITIONS
from lab_v4_dev.nlu.conversation_semantics import is_social_act, is_style_act


class DialogueMemory:
    """
    Conversation-owned dialogue coordinator.

    Responsibilities:
        - maintain DialogueState
        - maintain bounded dialogue history
        - resolve conversational references
        - manage pending topics

    Explicitly out of scope:
        - intent classification
        - routing
        - execution
        - provider selection
        - persistence
        - project/runtime state ownership
    """

    def __init__(self, context_store):
        self.context = context_store
        self.state = DialogueState()

    # --------------------------------------------------------
    # Compatibility properties
    # --------------------------------------------------------

    @property
    def last_topic(self):
        return self.state.last_topic

    @last_topic.setter
    def last_topic(self, value):
        self.state.last_topic = value

    @property
    def pending_topic(self):
        return self.state.pending_topic

    @pending_topic.setter
    def pending_topic(self, value):
        self.state.pending_topic = value

    @property
    def last_list(self):
        """Compatibility view of the bounded dialogue history."""
        history = getattr(self.state, "history", [])
        return list(history or [])

    @property
    def last_items(self):
        return self.state.last_items

    @last_items.setter
    def last_items(self, value):
        self.state.last_items = list(value or [])

    # --------------------------------------------------------
    # State lifecycle
    # --------------------------------------------------------


    def reset(self) -> None:
        """
        P06 — Reset dialogue-owned state.

        DialogueMemory owns DialogueState.
        Canonical execution ContextStore remains owned externally.
        """
        self.state = DialogueState()

    def update(
        self,
        text: str,
        result: dict,
        *,
        mode: str | None = None,
        parsed: dict | None = None,
        context_transition: str | None = None,
    ) -> None:

        if not isinstance(result, dict):
            return

        if not result.get("text"):
            return

        parsed = parsed or {}
        previous_context = self.active_context_entity()

        turn_intent = parsed.get("intent") or result.get("intent")
        turn_target = parsed.get("target") or result.get("target")
        turn_confidence = parsed.get("confidence", result.get("confidence", 0.0))
        relation = getattr(context_transition, "value", context_transition)
        conversation_act = parsed.get("conversation_act")
        preserve_active_subject = bool(
            self.state.last_topic
            and not turn_target
            and relation in {
                "ambiguous", "continue", "reference", "clarification",
            }
            and (
                is_social_act(conversation_act)
                or is_style_act(conversation_act)
            )
        )

        self.state.last_mode = mode or result.get("mode")
        if not preserve_active_subject:
            self.state.last_intent = turn_intent
            self.state.last_target = turn_target
            try:
                self.state.last_confidence = float(turn_confidence or 0.0)
            except (TypeError, ValueError):
                self.state.last_confidence = 0.0

        topic = self._derive_topic(text, turn_target)
        if context_transition is None:
            # Compatibility for direct legacy callers; the main conversation
            # path always supplies its explicit transition decision.
            update_topic = self.state.last_mode != "FOLLOW_UP" and bool(topic)
        else:
            update_topic = relation in {
                "explicit_switch",
                "new_independent",
                "restore",
            } and bool(topic)

        if update_topic:
            if (
                previous_context
                and not self._same_topic(previous_context.get("entity"), topic)
            ):
                self._remember_context(previous_context)
            self.state.last_topic = topic
            entity_type = parsed.get("entity_type") or result.get("entity_type")
            if not entity_type and turn_target:
                try:
                    from lab_v4_dev.nlu.entity_extractor import extract
                    intent_value = getattr(turn_intent, "value", turn_intent)
                    entity_type = extract(
                        str(turn_target),
                        str(intent_value or ""),
                    ).get("type")
                except Exception:
                    entity_type = None
            self.state.last_entity_type = entity_type or None
            if relation == "restore":
                self._forget_context(topic)
            if (
                self.state.pending_topic
                and self._same_topic(self.state.pending_topic, topic)
            ):
                self.state.pending_topic = None
        elif (
            context_transition is not None
            and relation in CONTEXTUAL_TRANSITIONS
            and not self.state.last_topic
            and topic
        ):
            self.state.last_topic = topic
            self.state.last_entity_type = parsed.get("entity_type") or None

        self.state.add_turn(
            role="user",
            content=text,
            mode=self.state.last_mode,
            intent=turn_intent,
            target=turn_target,
            confidence=turn_confidence,
        )

        self.state.add_turn(
            role="assistant",
            content=result.get("text", ""),
            mode=self.state.last_mode,
            intent=turn_intent,
            target=turn_target,
            confidence=turn_confidence,
        )

        items = result.get("items") or result.get("files") or []
        if items:
            self.state.last_items = list(items)

    def _derive_topic(self, text: str, target=None):
        if target:
            return str(target)

        for token in str(text).split():
            cleaned = token.strip(".,،؛:!?؟()[]{}\"'")
            if cleaned.endswith(".py"):
                return cleaned

        return text.strip() or None

    # --------------------------------------------------------
    # Topic lifecycle
    # --------------------------------------------------------

    @staticmethod
    def _same_topic(left, right) -> bool:
        def normalize(value):
            return " ".join(str(value or "").casefold().split())
        return bool(normalize(left)) and normalize(left) == normalize(right)

    def _remember_context(self, context: dict | None) -> None:
        if not isinstance(context, dict):
            return
        entity = context.get("entity")
        entity_type = str(context.get("entity_type") or "").upper()
        if not entity or entity_type in {"", "UNKNOWN", "REFERENCE", "ELABORATION"}:
            return
        entry = {
            "action": str(context.get("action") or ""),
            "entity": str(entity),
            "entity_type": entity_type,
        }
        previous = [
            item for item in self.state.context_history
            if not self._same_topic(item.get("entity"), entity)
        ]
        previous.append(entry)
        self.state.context_history = previous[-8:]

    def _forget_context(self, topic: str) -> None:
        self.state.context_history = [
            item for item in self.state.context_history
            if not self._same_topic(item.get("entity"), topic)
        ]

    def context_for_topic(self, topic: str | None) -> dict | None:
        """Return a previously validated subject only for an explicit target."""
        if not topic:
            return None
        for item in reversed(self.state.context_history):
            entity_type = str(item.get("entity_type") or "").upper()
            if (
                self._same_topic(item.get("entity"), topic)
                and entity_type not in {"", "UNKNOWN", "REFERENCE", "ELABORATION"}
            ):
                return dict(item)
        return None

    def save_pending(self, topic: str):
        self.state.pending_topic = topic
        active = self.active_context_entity()
        if active and self._same_topic(active.get("entity"), topic):
            self._remember_context(active)

    def restore_pending(self) -> str | None:
        topic = self.state.pending_topic
        self.state.pending_topic = None
        return topic

    def active_context_entity(self) -> dict | None:
        """Return the active dialogue subject for an already-approved transition."""
        topic = self.state.last_topic
        entity_type = self.state.last_entity_type
        entity_type = str(entity_type or "").upper()
        if not topic or entity_type in {
            "",
            "UNKNOWN", "REFERENCE", "ELABORATION",
        }:
            return None
        return {
            "action": self.state.last_intent or "",
            "entity": topic,
            "entity_type": entity_type,
        }

    # --------------------------------------------------------
    # Reference resolution
    # --------------------------------------------------------

    def resolve_references(
        self,
        text: str,
        *,
        context_entity: dict | None = None,
    ) -> str:
        """Make an already-authorized subject explicit without phrase rewrites."""
        text = str(text)
        topic = (
            context_entity.get("entity")
            if isinstance(context_entity, dict)
            else self.state.last_topic
        )
        if not topic:
            return text

        resolved = f"{topic} {text.strip()}"
        if "الحل الثاني" in text and len(self.state.last_items) >= 2:
            resolved = resolved.replace(
                "الحل الثاني",
                str(self.state.last_items[1]),
            )
        return resolved

    # --------------------------------------------------------
    # Read-only inspection
    # --------------------------------------------------------

    def snapshot(self) -> dict:
        return self.state.snapshot()
