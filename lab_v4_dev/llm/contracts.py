"""
P08 — Canonical LLM Gateway Contracts.

Provider implementations must communicate with the Gateway through
these contracts. Provider-specific SDK/HTTP details must not leak
above the provider adapter boundary.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    system: Optional[str] = None
    max_tokens: int = 800
    model: Optional[str] = None
    temperature: float = 0.3
    timeout_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMError:
    code: str
    message: str
    provider: Optional[str] = None
    retryable: bool = False
    timeout: bool = False
    details: Any = None


@dataclass
class LLMResponse:
    status: str
    text: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens: int = 0
    fallback_used: bool = False
    error: Optional[LLMError] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @classmethod
    def success(
        cls,
        text: str,
        provider: str,
        model: Optional[str] = None,
        tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        return cls(
            status="success",
            text=text or "",
            provider=provider,
            model=model,
            tokens=tokens or 0,
            metadata=metadata or {},
        )

    @classmethod
    def failure(
        cls,
        error: LLMError,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        return cls(
            status="error",
            provider=provider or error.provider,
            model=model,
            error=error,
            metadata=metadata or {},
        )

    @classmethod
    def fallback(
        cls,
        text: str,
        provider: str = "dummy",
        model: Optional[str] = "dummy",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        return cls(
            status="fallback",
            text=text or "",
            provider=provider,
            model=model,
            fallback_used=True,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class ProviderSelection:
    provider: str
    reason: str = ""
    model: Optional[str] = None
    fallback_chain: tuple = ()
