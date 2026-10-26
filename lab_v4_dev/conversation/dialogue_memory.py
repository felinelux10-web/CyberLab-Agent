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
        # A persisted dialogue snapshot is trusted only when it carries the
        # same explicit session identity used by its turns and exchanges.
        # Restoring topic metadata from a legacy snapshot without that identity
        # would still leak stale context even if its transcript were filtered.
        snapshot_session_id = str(snapshot.get("session_id") or "").strip()
        if not snapshot_session_id:
            return False

        restored = DialogueState()
        restored.session_id = snapshot_session_id
        for field in (
            "last_topic", "pending_topic", "pending_context", "last_mode", "last_intent",
            "last_target", "last_entity_type", "last_confidence",
            "pending_clarification", "last_items", "context_history",
            "exchange_archive",
        ):
            if field in snapshot:
                setattr(restored, field, snapshot[field])
        # Never relabel records without the exact checkpoint session identity.
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
        result_intent = getattr(result.get("intent"), "value", result.get("intent"))
        local_dialogue_result = (
            str(result.get("source") or "").casefold() == "local_dialogue_engine"
            and str(result.get("conversation_act") or "").upper() != "AGENT_IDENTITY"
        )
        local_social_result = (
            str(result.get("source") or "").casefold() == "local_social"
            and str(result_intent or "").casefold() in {"personal_chat", "chat"}
            and not str(result.get("target") or parsed.get("target") or "").strip()
        )
        conversation_domain = parsed.get(
            "conversation_domain", semantic.get("conversation_domain", "general")
        )
        conversation_act = parsed.get(
            "conversation_act", semantic.get("conversation_act", "NONE")
        )
        context_kind = semantic.get("context_kind", "unknown")
        # A locally handled social response has an unambiguous dialogue owner.
        # Do not let a conflicting fallback/parser domain (for example,
        # "execution") silently discard it from the dialogue archive.
        targetless_chat_dialogue = (
            str(mode or "").upper() == "CHAT"
            and str(getattr(parsed.get("intent"), "value", parsed.get("intent")) or "").casefold()
            in {"personal_chat", "chat", "discussion"}
            and not str(parsed.get("target") or result.get("target") or "").strip()
            and str(conversation_domain or "").casefold()
            not in {"work", "system", "execution"}
            and str(context_kind or "").casefold() not in {"work", "system", "execution"}
        )
        if local_dialogue_result:
            # This responder is called only after the dialogue owner has
            # authorized an offline conversational act. Its result must not be
            # discarded because the first-pass parser called it resume/system,
            # nor may it inherit a stale technical/project label.
            conversation_domain = "social"
            context_kind = "dialogue"
        elif local_social_result or targetless_chat_dialogue:
            # Targetless friendly chat belongs to the dialogue lifecycle whether
            # the reply was produced locally or by the configured language model.
            # Parser fallback labels must not silently classify it as execution.
            if str(conversation_domain or "").casefold() not in {"technical", "project"}:
                conversation_domain = "social"
            context_kind = "dialogue"

        turn_intent = (
            result.get("intent")
            if local_social_result or local_dialogue_result
            else parsed.get("intent") or result.get("intent")
        )
        # The canonical semantic request may contain the topic authorized by a
        # RESTORE transition even when the user did not name that topic again.
        # Persist that resolved target rather than treating "return to the
        # previous discussion" as a new topic or leaving the intervening branch active.
        turn_target = (
            (result.get("target") or None)
            if local_dialogue_result
            else (
                parsed.get("target")
                or result.get("target")
                or (
                    semantic.get("target")
                    if getattr(context_transition, "value", context_transition) == "restore"
                    else None
                )
            )
        )
        turn_confidence = parsed.get("confidence", result.get("confidence", 0.0))
        relation = getattr(context_transition, "value", context_transition)
        # Work/system turns belong to their own state owners. Do not let a
        # session report, restore command, or executable operation overwrite
        # the active friendly-dialogue topic or enter its durable archive.
        # Educational technical exchanges may still use the execution owner;
        # their technical domain keeps them eligible for dialogue continuity.
        if (
            str(context_kind or "").casefold() in {"work", "system"}
            or str(conversation_domain or "").casefold()
            in {"work", "system", "execution"}
            or (
                str(context_kind or "").casefold() == "execution"
                and str(conversation_domain or "").casefold() != "technical"
            )
        ):
            return

        resolved_intent_value = getattr(turn_intent, "value", turn_intent)
        if (
            relation == "restore"
            and str(resolved_intent_value or "").casefold()
            in {"personal_chat", "chat", "discussion", "question"}
            and turn_target
        ):
            restored_context = self.context_for_topic(str(turn_target))
            if not isinstance(restored_context, dict):
                # A compact archive may outlive context_history. Reconstruct
                # only from a same-session exchange with the exact target.
                session_id = str(getattr(self.state, "session_id", "") or "")
                archived = next(
                    (
                        item for item in reversed(getattr(self.state, "exchange_archive", []) or [])
                        if isinstance(item, dict)
                        and str(item.get("session_id") or "") == session_id
                        and str(item.get("target") or "").strip() == str(turn_target).strip()
                        and str(item.get("intent") or "").strip()
                    ),
                    None,
                )
                if archived:
                    restored_context = {
                        "entity": str(turn_target),
                        "action": str(archived.get("intent") or ""),
                        "entity_type": (
                            "CONCEPT"
                            if str(archived.get("conversation_domain") or "").casefold() == "technical"
                            else "UNKNOWN"
                        ),
                    }
            if isinstance(restored_context, dict) and restored_context.get("action"):
                # A targetless return is routed as chat to avoid a fresh
                # explanation, but state ownership must still reactivate the
                # restored branch's original intent for the next continuation.
                turn_intent = restored_context["action"]
        conversation_act = parsed.get("conversation_act")
        if local_dialogue_result:
            conversation_act = result.get("conversation_act") or conversation_act or "CONVERSATION_CONTINUATION"
        elif local_social_result and str(conversation_act or "NONE").upper() == "NONE":
            conversation_act = "CASUAL_CONVERSATION"
        # Recall is read-only: storing the retrieval request and its summary as
        # a new exchange would make the memory report itself as the latest topic
        # and could replace the active intent used by the next continuation.
        if str(conversation_act or "").upper() == "CONVERSATION_HISTORY_QUERY":
            return

        # A failed response must never be stored as an assistant answer or as
        # a resumable exchange. However, an explicit named branch switch is
        # still a valid user state transition; preserve that topic and user
        # turn so the next "continue" resolves to the new branch. Keep generic
        # failed chat turns out of dialogue history entirely.
        if provider_failed and parsed.get("semantic_pattern") == "COMPOUND_DIALOGUE_REQUEST":
            # Preserve the user's compound prompt for later factual recall when
            # the provider fails, but never archive the fallback/error as an answer
            # or treat the failed exchange as resumable prompt context.
            archive = [
                item for item in (getattr(self.state, "exchange_archive", []) or [])
                if isinstance(item, dict)
                and str(item.get("session_id") or "") == self.state.session_id
            ]
            archive.append({
                "user": str(text),
                "assistant": "",
                "intent": getattr(turn_intent, "value", turn_intent),
                "target": None,
                "conversation_domain": conversation_domain,
                "conversation_act": conversation_act or "NONE",
                "context_kind": context_kind if context_kind in {"dialogue", "social"} else "dialogue",
                "context_transition": relation,
                "session_id": self.state.session_id,
                "recall_only": True,
                "response_failed": True,
            })
            self.state.exchange_archive = archive[-32:]

        if provider_failed and not (
            turn_target
            and relation in {"explicit_switch", "new_independent", "restore"}
        ):
            # Even if a provider fails, a subjectless independent social opening
            # still closes the old branch. Do not archive the failed exchange, but
            # do not let the next turn inherit the previous technical subject.
            if (
                relation == "new_independent"
                and not turn_target
                and context_kind in {"dialogue", "social"}
            ):
                if previous_context:
                    self._remember_context(previous_context)
                self.state.last_mode = mode or result.get("mode")
                self.state.last_intent = turn_intent
                self.state.last_target = None
                self.state.last_topic = None
                self.state.last_entity_type = None
                try:
                    self.state.last_confidence = float(turn_confidence or 0.0)
                except (TypeError, ValueError):
                    self.state.last_confidence = 0.0
                # Retain a content-free boundary so the next continuation cannot
                # fall back into the previous branch when the provider is offline.
                # The failed user/assistant exchange itself is not stored.
                archive = [
                    item for item in (getattr(self.state, "exchange_archive", []) or [])
                    if isinstance(item, dict)
                    and str(item.get("session_id") or "") == self.state.session_id
                ]
                archive.append({
                    "user": "",
                    "assistant": "",
                    "intent": getattr(turn_intent, "value", turn_intent),
                    "target": None,
                    "conversation_domain": conversation_domain,
                    "conversation_act": conversation_act or "CASUAL_CONVERSATION",
                    "context_kind": context_kind,
                    "context_transition": "new_independent",
                    "session_id": self.state.session_id,
                    "state_boundary_only": True,
                })
                self.state.exchange_archive = archive[-32:]
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
                or str(conversation_act or "").upper() in {
                    "TOPIC_CONTINUATION_QUERY",
                    "CONVERSATION_CONTINUATION",
                }
            )
            or (
                previous_context
                and str(result_intent or "").casefold()
                in {"health", "self_diagnose", "full_diagnose", "run_diagnostics"}
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
            or is_social_act(conversation_act)
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
            if str(entity_type or "").upper() in {
                "", "UNKNOWN", "REFERENCE", "ELABORATION",
            } and turn_target and str(parsed.get("entity_type") or "").upper() not in {
                "UNKNOWN", "REFERENCE", "ELABORATION",
            }:
                restored_context = self.context_for_topic(str(turn_target))
                if restored_context:
                    entity_type = restored_context.get("entity_type")
            if (
                str(entity_type or "").upper() in {
                "", "UNKNOWN", "REFERENCE", "ELABORATION",
                }
                and turn_target
                and str(parsed.get("entity_type") or "").upper()
                not in {"UNKNOWN", "REFERENCE", "ELABORATION"}
            ):
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
        # The exchange archive is authoritative when a compact/legacy
        # snapshot did not rebuild context_history.
        session_id = str(getattr(self.state, "session_id", "") or "")
        for item in reversed(self.state.exchange_archive or []):
            if not isinstance(item, dict) or item.get("recall_only"):
                continue
            if session_id and str(item.get("session_id") or "") != session_id:
                continue
            if not self._same_topic(item.get("target"), topic):
                continue
            domain = str(item.get("conversation_domain") or "general").casefold()
            kind = str(item.get("context_kind") or "dialogue").casefold()
            if domain in {"work", "system", "execution"} or kind in {"work", "system"}:
                continue
            return {
                "action": item.get("intent") or "personal_chat",
                "entity": str(item.get("target") or topic),
                "entity_type": item.get("entity_type") or "CONCEPT",
                "conversation_domain": domain,
                "context_kind": kind,
            }
        return None

    def save_pending(self, topic: str):
        self.state.pending_topic = topic
        active = self.active_context_entity()
        self.state.pending_context = dict(active) if active else None
        if active and self._same_topic(active.get("entity"), topic):
            self._remember_context(active)

    def restore_pending(self) -> str | None:
        topic = self.state.pending_topic
        self.state.pending_topic = None
        self.state.pending_context = None
        return topic

    def active_dialogue_branch(self) -> dict | None:
        """Return the latest same-session dialogue branch with owner metadata."""
        state = self.state
        session_id = str(getattr(state, "session_id", "") or "")
        active = self.active_context_entity()
        for item in reversed(state.exchange_archive or []):
            if not isinstance(item, dict) or item.get("recall_only"):
                continue
            if session_id and str(item.get("session_id") or "") != session_id:
                continue
            domain = str(item.get("conversation_domain") or "general").casefold()
            kind = str(item.get("context_kind") or "dialogue").casefold()
            if domain in {"work", "system", "execution"} or kind in {"work", "system"}:
                continue
            target = str(item.get("target") or "").strip()
            if not target and any(
                isinstance(previous, dict)
                and str(previous.get("target") or "").strip()
                and str(previous.get("session_id") or "") == session_id
                for previous in (state.exchange_archive or [])
            ):
                # Style/acknowledgement turns are not a new branch. Preserve
                # the latest named branch for the next reference or follow-up.
                continue
            if active and target and self._same_topic(target, active.get("entity")):
                branch = dict(active)
            else:
                branch = {
                    "action": item.get("intent") or "personal_chat",
                    "entity": target or None,
                    "entity_type": item.get("entity_type") or ("CONCEPT" if target else "REFERENCE"),
                }
            branch.update({
                "conversation_domain": domain,
                "context_kind": kind,
                "reference_text": item.get("assistant") or item.get("user") or "",
            })
            return branch
        return None

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

    def interrupted_branch_exchanges(self) -> list[dict]:
        """Select the archived dialogue branch immediately before the latest switch."""
        state = self.state
        session_id = str(getattr(state, "session_id", "") or "")
        valid = [
            dict(item) for item in (getattr(state, "exchange_archive", []) or [])
            if isinstance(item, dict)
            and str(item.get("session_id") or "") == session_id
            and str(item.get("context_kind") or "").casefold() not in {"work", "system"}
            and (
                str(item.get("context_kind") or "").casefold() != "execution"
                or str(item.get("conversation_domain") or "").casefold() == "technical"
            )
            and str(item.get("conversation_domain") or "").casefold()
            not in {"work", "system", "execution"}
            and not any(marker in str(item.get("user") or "").casefold() for marker in (
                "استرجع النقاش الذي انقطع", "استرجع الحوار الذي انقطع",
                "recover the interrupted discussion",
            ))
        ]
        if not valid:
            return []

        def boundary(item):
            transition = str(item.get("context_transition") or "").casefold()
            if transition in {"new_independent", "explicit_switch", "restore"}:
                return transition
            user = str(item.get("user") or "").casefold().replace("أ", "ا").replace("إ", "ا")
            if any(marker in user for marker in (
                "لنغير الموضوع", "نغير الموضوع", "غير الموضوع",
                "ننتقل الى موضوع", "لننتقل الى موضوع", "change the topic",
                "change the subject",
            )):
                return "explicit_switch"
            if any(marker in user for marker in (
                "مستقل عن الموضوع السابق", "موضوع جديد", "موضوع مختلف",
                "independent topic", "new topic", "different topic",
            )):
                return "new_independent"
            if any(marker in user for marker in (
                "نرجع الى موضوع", "نرجع إلى موضوع", "ارجع الى موضوع",
                "ارجع إلى موضوع", "back to ", "return to ",
            )):
                return "restore"
            return ""

        boundaries = [
            (index, boundary(item)) for index, item in enumerate(valid)
            if boundary(item) in {"new_independent", "explicit_switch", "restore"}
        ]
        if not boundaries:
            return valid[-4:]
        latest_index, latest_kind = boundaries[-1]
        if latest_kind == "restore":
            selected = valid[latest_index:]
        elif len(boundaries) > 1:
            selected = valid[boundaries[-2][0]:latest_index]
        elif latest_index > 0:
            selected = valid[:latest_index]
        else:
            selected = valid[-4:]
        return selected[-4:]

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
