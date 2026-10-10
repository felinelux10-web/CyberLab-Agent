"""
Semantic Request Contract — Conversation Phase A.

Model-independent contract between natural-language conversation and the
planning/execution layers.

This module describes what was understood. It does not execute tools,
select providers, mutate files, or bypass existing safety controls.
"""
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Optional


MODES = frozenset({
    "CHAT",
    "QUESTION",
    "DISCUSSION",
    "FOLLOW_UP",
    "TASK",
    "SYSTEM",
})

ACTION_TYPES = frozenset({
    "none",
    "read",
    "analyze",
    "modify",
    "execute",
    "manage",
})

CONVERSATION_DOMAINS = frozenset({
    "general", "social", "style", "execution", "technical", "project", "system",
    "agent_self",
})

CONTEXT_KINDS = frozenset({
    "dialogue", "work", "project", "personal", "social", "system", "unknown",
})

CONVERSATION_ACTS = frozenset({
    "NONE",
    "EXECUTABLE_REQUEST",
    "GENERAL_CHAT",
    "CASUAL_CONVERSATION",
    "SOCIAL_GREETING",
    "SOCIAL_ACKNOWLEDGEMENT",
    "SOCIAL_CLOSING",
    "SOCIAL_OPENING",
    "ASSISTANT_STATE_QUERY",
    "ASSISTANT_CAPABILITY_QUERY",
    "ASSISTANT_IDENTITY_QUERY",
    "AGENT_ARCHITECTURE_QUERY",
    "AGENT_EXECUTION_FLOW_QUERY",
    "AGENT_LIMITS_QUERY",
    "TOPIC_CONTINUATION_QUERY",
    "PERSONAL_INTERACTION",
    "CASUAL_DISCUSSION",
    "SOCIAL_FOLLOW_UP",
    "SIMPLIFICATION_REQUEST",
    "VERBOSITY_REQUEST",
    "FORMALITY_REQUEST",
    "TONE_REQUEST",
    "STYLE_REQUEST",
    "TOPIC_SHIFT",
    "TOPIC_RETURN",
    "CORRECTION",
    "COMPOUND_REFERENCE",
    "CONVERSATION_CONTINUATION",
    "CONVERSATION_HISTORY_QUERY",
})


class ContextTransition(str, Enum):
    """Conversation-owned relationship between the current turn and topic."""

    CONTINUE = "continue"
    REFERENCE = "reference"
    CLARIFICATION = "clarification"
    RESTORE = "restore"
    EXPLICIT_SWITCH = "explicit_switch"
    NEW_INDEPENDENT = "new_independent"
    AMBIGUOUS = "ambiguous"


CONTEXTUAL_TRANSITIONS = frozenset({
    ContextTransition.CONTINUE.value,
    ContextTransition.REFERENCE.value,
    ContextTransition.CLARIFICATION.value,
    ContextTransition.RESTORE.value,
})
CONTEXT_TRANSITIONS = frozenset(item.value for item in ContextTransition)

_NON_EXECUTABLE_AGENT_INTENTS = frozenset({
    "agent_identity",
    "agent_capabilities",
    "agent_architecture",
    "agent_execution_flow",
    "agent_limits",
})


@dataclass(frozen=True)
class SemanticRequest:
    raw: str
    mode: str
    intent: Optional[str] = None
    conversation_domain: str = "general"
    conversation_act: str = "NONE"
    conversation_confidence: float = 0.0
    response_attributes: Dict[str, Any] | None = None
    action_type: str = "none"
    confidence: float = 0.0
    ambiguity: bool = False
    compound: bool = False
    requires_context: bool = False
    context_transition: str = ContextTransition.AMBIGUOUS.value
    requires_planning: bool = False
    target: Optional[str] = None
    context_kind: str = "unknown"

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"invalid semantic mode: {self.mode}")
        if self.action_type not in ACTION_TYPES:
            raise ValueError(f"invalid action type: {self.action_type}")
        if self.context_kind not in CONTEXT_KINDS:
            raise ValueError(f"invalid context kind: {self.context_kind}")
        if self.conversation_domain not in CONVERSATION_DOMAINS:
            raise ValueError(f"invalid conversation domain: {self.conversation_domain}")
        if self.conversation_act not in CONVERSATION_ACTS:
            raise ValueError(f"invalid conversation act: {self.conversation_act}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= float(self.conversation_confidence) <= 1.0:
            raise ValueError("conversation_confidence must be between 0 and 1")
        if self.context_transition not in CONTEXT_TRANSITIONS:
            raise ValueError(
                f"invalid context transition: {self.context_transition}"
            )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def action_type_for_mode(mode: str) -> str:
    if mode == "TASK":
        return "execute"
    if mode == "SYSTEM":
        return "manage"
    if mode in {"QUESTION", "DISCUSSION"}:
        return "analyze"
    return "none"


def build_semantic_request(
    raw: str,
    mode: str,
    *,
    intent: Optional[str] = None,
    conversation_domain: str = "general",
    conversation_act: str = "NONE",
    conversation_confidence: float = 0.0,
    response_attributes: Dict[str, Any] | None = None,
    confidence: float = 0.5,
    target: Optional[str] = None,
    ambiguity: bool = False,
    compound: bool = False,
    requires_context: bool = False,
    context_transition: str = ContextTransition.AMBIGUOUS.value,
    requires_planning: Optional[bool] = None,
    context_kind: str = "unknown",
) -> SemanticRequest:
    if requires_planning is None:
        requires_planning = compound or mode == "TASK"

    return SemanticRequest(
        raw=raw,
        mode=mode,
        intent=intent,
        conversation_domain=conversation_domain,
        conversation_act=conversation_act,
        conversation_confidence=conversation_confidence,
        response_attributes=dict(response_attributes or {}),
        action_type=(
            "none"
            if intent in _NON_EXECUTABLE_AGENT_INTENTS
            else action_type_for_mode(mode)
        ),
        confidence=confidence,
        ambiguity=ambiguity,
        compound=compound,
        requires_context=requires_context,
        context_transition=(
            context_transition.value
            if isinstance(context_transition, ContextTransition)
            else context_transition
        ),
        requires_planning=requires_planning,
        target=target,
        context_kind=context_kind,
    )
