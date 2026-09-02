from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class AuditEvent:
    """Minimal contract for P014 audit events (compatible with EventRecord)."""
    timestamp: str
    event: str
    source: str
    context: Dict[str, Any]
    details: Dict[str, Any]


# Append to existing __all__ if present; if not, consumers can import directly
try:
    __all__.append("AuditEvent")
except Exception:
    __all__ = ["AuditEvent"]
