"""
P04 — Canonical Intent Semantic Contract.

Interpretation-only contract.
No routing, execution, provider, or business logic belongs here.
"""

from __future__ import annotations

from typing import Any, Mapping


INTENT_RESULT_KEYS = (
    "intent",
    "confidence",
    "target",
    "action",
    "context",
    "raw",
)


class IntentResult(dict):
    """Canonical Intent result with legacy dict compatibility."""

    __slots__ = ()

    def __init__(
        self,
        *,
        intent: str,
        confidence: float = 0.0,
        target: str = "",
        action: str = "",
        context: str = "general",
        raw: str = "",
        **extra: Any,
    ) -> None:
        super().__init__(
            intent=intent,
            confidence=float(confidence),
            target=target or "",
            action=action or "",
            context=context or "general",
            raw=raw or "",
        )
        self.update(extra)

    def validate(self) -> bool:
        return (
            isinstance(self.get("intent"), str)
            and isinstance(self.get("confidence"), (int, float))
            and 0.0 <= float(self["confidence"]) <= 1.0
            and isinstance(self.get("target"), str)
            and isinstance(self.get("action"), str)
            and isinstance(self.get("context"), str)
            and isinstance(self.get("raw"), str)
        )

    @classmethod
    def from_mapping(cls, result: Mapping[str, Any]) -> "IntentResult":
        data = dict(result)
        return cls(
            intent=data.pop("intent", "unsupported"),
            confidence=data.pop("confidence", 0.0),
            target=data.pop("target", ""),
            action=data.pop("action", ""),
            context=data.pop("context", "general"),
            raw=data.pop("raw", ""),
            **data,
        )



def to_legacy(value):
    """
    Convert the unified IntentResult/IntentResolution contract back to
    the historical dictionary representation for legacy consumers.
    """
    if isinstance(value, dict):
        return dict(value)

    if not isinstance(value, IntentResult):
        raise TypeError("intent result must be IntentResult-compatible")

    return {
        "intent": value.get("intent", ""),
        "target": value.get("target", ""),
        "context": value.get("context", {}),
        "confidence": value.get("confidence", 0.0),
        "raw": value.get("raw", ""),
    }


def from_legacy(value):
    """
    Preserve the exact legacy mapping while exposing IntentResolution
    attribute access and validation.
    """
    if isinstance(value, IntentResolution):
        return value

    if isinstance(value, IntentResult):
        value = dict(value)

    if not isinstance(value, dict):
        raise TypeError("legacy intent result must be a dict")

    # Construct through the unified contract, then restore the exact
    # original mapping so defaults never leak into legacy roundtrips.
    result = IntentResolution(**dict(value))
    result.clear()
    result.update(dict(value))
    return result


def to_legacy(value):
    """
    Restore the exact original legacy mapping.
    """
    if isinstance(value, dict):
        return dict(value)

    if not isinstance(value, IntentResult):
        raise TypeError("intent result must be IntentResult-compatible")

    return dict(value)


class IntentResolution(IntentResult):
    """
    Backward-compatible semantic resolution contract.

    Provides both mapping-style access and attribute-style access required
    by legacy P01 consumers.
    """

    @property
    def intent(self):
        return self.get("intent", "")

    @property
    def confidence(self):
        return self.get("confidence", 0.0)

    @property
    def target(self):
        return self.get("target", "")

    @property
    def action(self):
        return self.get("action", "")

    @property
    def context(self):
        return self.get("context", {})

    @property
    def raw(self):
        return self.get("raw", "")
