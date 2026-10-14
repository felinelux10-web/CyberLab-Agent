"""
P05 — Dialogue Memory.

Owns dialogue state and reference resolution.
Does not route, execute, call providers, or decide intent.
"""

from __future__ import annotations

import uuid

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

    def restore_snapshot(self, snapshot: dict | None) -> bool:
        """Restore bounded dialogue state from an explicit recoverable checkpoint."""
        if not isinstance(snapshot, dict):
            return False
        restored = DialogueState()
        restored.session_id = str(snapshot.get("session_id") or uuid.uuid4().hex)
        for field in (
            "last_topic", "pending_topic", "last_mode", "last_intent",
            "last_target", "last_entity_type", "last_confidence",
            "pending_clarification", "last_items", "context_history",
            "exchange_archive",
        ):
            if field in snapshot:
                setattr(restored, field, snapshot[field])
        # Missing session IDs are untrusted legacy data. Never relabel them as
        # belonging to the current session: that can import old technical turns.
        restored.exchange_archive = [
            dict(item)
            for item in (restored.exchange_archive or [])
            if isinstance(item, dict)
            and str(item.get("session_id") or "") == restored.session_id
        ][-32:]
        for turn in (snapshot.get("history") or [])[-8:]:
            if not isinstance(turn, dict) or not turn.get("role"):
                continue
            # A turn without an explicit session ID cannot safely be attributed
            # to this session, even when it came from an older checkpoint.
            turn_session_id = str(turn.get("session_id") or "")
            if turn_session_id != restored.session_id:
                continue
            restored.add_turn(
                role=turn.get("role", ""),
                content=turn.get("content", ""),
                mode=turn.get("mode"),
                intent=turn.get("intent"),
                target=turn.get("target"),
                confidence=turn.get("confidence", 0.0),
                conversation_domain=turn.get("conversation_domain", "general"),
                conversation_act=turn.get("conversation_act", "NONE"),
                context_kind=turn.get("context_kind", "unknown"),
                session_id=turn.get("session_id") or restored.session_id,
            )
        self.state = restored
        return True

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
        provider_failed = (
            str(result.get("status") or "").casefold()
            in {"error", "failed", "failure", "provider_error"}
            or bool(result.get("error"))
        )
        parsed = parsed or {}
        previous_context = self.active_context_entity()

        semantic = result.get("semantic_request") or {}
        conversation_domain = parsed.get(
            "conversation_domain", semantic.get("conversation_domain", "general")
        )
        conversation_act = parsed.get(
            "conversation_act", semantic.get("conversation_act", "NONE")
        )
        context_kind = semantic.get("context_kind", "unknown")

        turn_intent = parsed.get("intent") or result.get("intent")
        # The canonical semantic request may contain the topic authorized by a
        # RESTORE transition even when the user did not name that topic again.
        # Persist that resolved target rather than treating "return to the
        # previous discussion" as a new topic or leaving the intervening branch active.
        turn_target = (
            parsed.get("target")
            or result.get("target")
            or semantic.get("target")
        )
        turn_confidence = parsed.get("confidence", result.get("confidence", 0.0))
        relation = getattr(context_transition, "value", context_transition)
        conversation_act = parsed.get("conversation_act")
        # A failed response must never be stored as an assistant answer or as
        # a resumable exchange. However, an explicit named branch switch is
        # still a valid user state transition; preserve that topic and user
        # turn so the next "continue" resolves to the new branch. Keep generic
        # failed chat turns out of dialogue history entirely.
        if provider_failed and not (
            turn_target
            and relation in {"explicit_switch", "new_independent", "restore"}
        ):
            return
        # Keep one compact user/assistant exchange for recall. This survives
        # the shorter prompt transcript without making every old turn part of
        # an LLM request. Failed/provider-error responses are not resumable.
        if (
            result.get("status") in (None, "success")
            and result.get("text")
            and result.get("source") != "fallback"
            and not result.get("error")
        ):
            exchange = {
                "user": str(text),
                "assistant": str(result.get("text")),
                "intent": getattr(turn_intent, "value", turn_intent),
                "target": turn_target,
                "conversation_domain": conversation_domain,
                "conversation_act": conversation_act or semantic.get("conversation_act", "NONE"),
                "context_kind": context_kind,
                "context_transition": relation,
                "session_id": self.state.session_id,
            }
            archive = [
                item for item in (getattr(self.state, "exchange_archive", []) or [])
                if isinstance(item, dict)
                and str(item.get("session_id") or self.state.session_id) == self.state.session_id
            ]
            archive.append(exchange)
            self.state.exchange_archive = archive[-32:]
        short_confirmation = str(text or "").strip().casefold() in {
            "نعم", "أجل", "اجل", "بلى", "لا", "كلا", "yes", "no",
        }
        preserve_active_subject = bool(
            self.state.last_topic
            and not turn_target
            and relation in {
                "ambiguous", "continue", "reference", "clarification",
            }
            and (
                short_confirmation
                or is_social_act(conversation_act)
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
        # A targetless social/dialogue utterance is not itself a stable topic.
        # Treating the entire sentence as an entity poisons active-context
        # detection and makes later continuations look like missing work context.
        if not turn_target and (
            context_kind in {"dialogue", "social"}
            or conversation_domain in {"general", "social", "agent_self"}
        ):
            topic = None

        # An explicit independent conversational branch with no canonical entity
        # must not leave the previous technical topic marked as active. Preserve
        # that prior entity in history so an explicit return can still restore it.
        if (
            relation in {"new_independent", "explicit_switch"}
            and not turn_target
            and context_kind in {"dialogue", "social"}
        ):
            if previous_context:
                self._remember_context(previous_context)
            self.state.last_topic = None
            self.state.last_entity_type = None

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
            conversation_domain=conversation_domain,
            conversation_act=conversation_act,
            context_kind=context_kind,
            session_id=self.state.session_id,
        )

        if (
            result.get("status") in {None, "success", "needs_clarification"}
            and result.get("text")
            and result.get("source") != "fallback"
            and not result.get("error")
        ):
            self.state.add_turn(
                role="assistant",
                content=result.get("text", ""),
                mode=self.state.last_mode,
                intent=turn_intent,
                target=turn_target,
                confidence=turn_confidence,
                conversation_domain=conversation_domain,
                conversation_act=conversation_act,
                context_kind=context_kind,
                session_id=self.state.session_id,
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

    def previous_context_entity(self) -> dict | None:
        """Return the latest side-branch subject available for a topic return."""
        if not self.state.context_history:
            return None
        item = self.state.context_history[-1]
        if not isinstance(item, dict):
            return None
        return dict(item)

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
        ordinal_items = {
            "الحل الثاني": 1,
            "النقطة الثانية": 1,
            "الجزء الثاني": 1,
            "النقطة 2": 1,
            "الجزء 2": 1,
            "الحل الأول": 0,
            "النقطة الأولى": 0,
            "الجزء الأول": 0,
            "النقطة 1": 0,
            "الجزء 1": 0,
        }
        for marker, index in ordinal_items.items():
            if marker in text and len(self.state.last_items) > index:
                resolved = resolved.replace(marker, str(self.state.last_items[index]))
                break
        return resolved

    # --------------------------------------------------------
    # Read-only inspection
    # --------------------------------------------------------

    def snapshot(self) -> dict:
        return self.state.snapshot()
