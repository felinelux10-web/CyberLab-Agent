"""
P05 — Dialogue State Contract.

Conversation-owned state only.
No routing, execution, provider, or persistence logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DialogueTurn:
    role: str
    content: str
    mode: str | None = None
    intent: str | None = None
    target: str | None = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "mode": self.mode,
            "intent": self.intent,
            "target": self.target,
            "confidence": self.confidence,
        }


@dataclass
class DialogueState:
    """
    Canonical conversation-owned dialogue state.

    Ownership boundary:
        - Conversation layer may create/update/read dialogue state.
        - Intent, NLU, Orchestrator, Executor and LLM must not own it.
        - Persistence is intentionally outside this contract.
        - Runtime/Project context are separate state domains.
    """
    last_topic: str | None = None
    pending_topic: str | None = None
    last_mode: str | None = None
    last_intent: str | None = None
    last_target: str | None = None
    last_entity_type: str | None = None
    last_confidence: float = 0.0
    pending_clarification: dict[str, Any] | None = None
    turns: list[DialogueTurn] = field(default_factory=list)
    last_items: list[Any] = field(default_factory=list)
    context_history: list[dict[str, str]] = field(default_factory=list)

    def add_turn(
        self,
        *,
        role: str,
        content: str,
        mode: str | None = None,
        intent: str | None = None,
        target: str | None = None,
        confidence: float = 0.0,
    ) -> None:
        self.turns.append(
            DialogueTurn(
                role=role,
                content=content,
                mode=mode,
                intent=intent,
                target=target,
                confidence=float(confidence),
            )
        )
        self.turns = self.turns[-8:]

    @property
    def history(self) -> list[dict[str, Any]]:
        return [turn.to_dict() for turn in self.turns]

    def snapshot(self) -> dict[str, Any]:
        return {
            "last_topic": self.last_topic,
            "pending_topic": self.pending_topic,
            "last_mode": self.last_mode,
            "last_intent": self.last_intent,
            "last_target": self.last_target,
            "last_entity_type": self.last_entity_type,
            "last_confidence": self.last_confidence,
            "pending_clarification": self.pending_clarification,
            "messages": len(self.turns),
            "history": self.history,
            "last_items": list(self.last_items),
            "context_history": [dict(item) for item in self.context_history],
        }
