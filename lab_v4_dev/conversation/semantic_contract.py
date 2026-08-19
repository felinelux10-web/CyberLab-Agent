"""
Semantic Request Contract — Conversation Phase A.

Model-independent contract between natural-language conversation and the
planning/execution layers.

This module describes what was understood. It does not execute tools,
select providers, mutate files, or bypass existing safety controls.
"""
from dataclasses import asdict, dataclass
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


@dataclass(frozen=True)
class SemanticRequest:
    raw: str
    mode: str
    action_type: str = "none"
    confidence: float = 0.0
    ambiguity: bool = False
    compound: bool = False
    requires_context: bool = False
    requires_planning: bool = False
    target: Optional[str] = None

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"invalid semantic mode: {self.mode}")
        if self.action_type not in ACTION_TYPES:
            raise ValueError(f"invalid action type: {self.action_type}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

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
    confidence: float = 0.5,
    target: Optional[str] = None,
    ambiguity: bool = False,
    compound: bool = False,
    requires_context: bool = False,
    requires_planning: Optional[bool] = None,
) -> SemanticRequest:
    if requires_planning is None:
        requires_planning = compound or mode == "TASK"

    return SemanticRequest(
        raw=raw,
        mode=mode,
        action_type=action_type_for_mode(mode),
        confidence=confidence,
        ambiguity=ambiguity,
        compound=compound,
        requires_context=requires_context,
        requires_planning=requires_planning,
        target=target,
    )
