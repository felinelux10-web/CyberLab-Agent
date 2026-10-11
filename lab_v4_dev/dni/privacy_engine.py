"""
DNI Privacy Engine - deterministic local classifier & sanitizer

Responsibilities (minimal, deterministic):
- Detect common secret patterns locally (API keys, tokens, passwords, private keys, synthetic test secrets)
- Provide structured inspect() result:
    {
        "allow_external": bool,
        "privacy_level": "public"|"normal"|"sensitive"|"secret"|"blocked",
        "sanitized": "<sanitized_text>",
        "reasons": [...],
        "redactions": [{"start":i,"end":j,"replacement":"[REDACTED:TYPE]"} ...]
    }

Design constraints:
- Purely local regex-based detection (no external calls)
- Conservative: do not redact normal code unless matched by secret patterns
- Deterministic and auditable
"""

import re
from typing import List, Dict

# Patterns (conservative)
_PATTERNS = {
    "API_KEY_GENERIC": re.compile(r"\b(?:api[_-]?key|apikey|apiKey)\s*[:=]\s*['\"]?([A-Za-z0-9\-_]{16,128})['\"]?", re.IGNORECASE),
    "BEARER_TOKEN": re.compile(r"\bBearer\s+[A-Za-z0-9\-\._~\+/=]{8,}", re.IGNORECASE),
    "SECRET_SK": re.compile(r"\bsk[_-][A-Za-z0-9\-_]{16,128}\b", re.IGNORECASE),
    "AWS_AKIA": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "PRIVATE_KEY_PEM": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    "PASSWORD_ASSIGN": re.compile(r"\bpassword\s*[:=]\s*['\"]?(.{4,200})['\"]?", re.IGNORECASE),
    "AUTH_HEADER": re.compile(r"authorization\s*[:=]\s*['\"]?.{8,300}['\"]?", re.IGNORECASE),
    "SYNTH_TEST_SECRET": re.compile(r"\bDNI_RUNTIME_TEST_SECRET_[0-9A-Za-z_]+\b"),
    # simple token-like strings used in tests
    "LONG_TOKEN": re.compile(r"\b[A-Za-z0-9]{32,}\b"),
}

# Map to privacy levels
_PATTERN_SEVERITY = {
    "PRIVATE_KEY_PEM": "secret",
    "API_KEY_GENERIC": "sensitive",
    "BEARER_TOKEN": "secret",
    "SECRET_SK": "secret",
    "AWS_AKIA": "secret",
    "PASSWORD_ASSIGN": "secret",
    "AUTH_HEADER": "secret",
    "SYNTH_TEST_SECRET": "secret",
    "LONG_TOKEN": "sensitive",
}

def _find_matches(text: str):
    reasons = []
    redactions = []
    for name, pattern in _PATTERNS.items():
        for m in pattern.finditer(text):
            span = m.span()
            # Avoid including the full matched secret in reasons; only store span
            severity = _PATTERN_SEVERITY.get(name, "sensitive")
            reasons.append({
                "type": name,
                "span": span,
                "severity": severity
            })
            redactions.append({
                "start": span[0],
                "end": span[1],
                "replacement": f"[REDACTED:{name}]"
            })
    return reasons, redactions

def _apply_redactions(text: str, redactions: List[Dict]) -> str:
    if not redactions:
        return text

    # Regexes can overlap (AUTH_HEADER, BEARER_TOKEN, and LONG_TOKEN may all
    # match one credential). Merge spans before replacing so no secret fragment
    # is duplicated or left visible by overlapping replacements.
    ordered = sorted(redactions, key=lambda item: (item["start"], -item["end"]))
    merged = []
    for item in ordered:
        start, end = int(item["start"]), int(item["end"])
        if start < 0 or end <= start or end > len(text):
            continue
        if not merged or start >= merged[-1]["end"]:
            merged.append({
                "start": start,
                "end": end,
                "replacement": item["replacement"],
                "span_length": end - start,
            })
            continue

        current = merged[-1]
        if end > current["end"]:
            current["end"] = end
        if end - start > current["span_length"]:
            current["replacement"] = item["replacement"]
            current["span_length"] = end - start

    parts = []
    last = len(text)
    for item in reversed(merged):
        parts.append(text[item["end"]:last])
        parts.append(item["replacement"])
        last = item["start"]
    parts.append(text[:last])
    return "".join(reversed(parts))

class PrivacyEngine:

    def __init__(self):
        self.version = "DNI-10.001"

    def sanitize(self, text: str) -> str:
        """
        Return a sanitized copy where detected secrets are redacted.
        Use a conservative redaction policy: only redact explicit matches.
        """
        if not text:
            return text
        _, redactions = _find_matches(text)
        return _apply_redactions(text, redactions)

    def inspect(self, text: str) -> dict:
        """
        Deterministic local inspection.
        Returns structured metadata and sanitized text.
        """
        if not isinstance(text, str):
            text = str(text or "")
        reasons, redactions = _find_matches(text)

        # Determine highest severity
        level = "public"
        allow_external = True
        for r in reasons:
            sev = r.get("severity", "sensitive")
            if sev == "secret":
                level = "blocked"
                allow_external = False
                break
            elif sev == "sensitive" and level != "blocked":
                level = "sensitive"
                # still may allow external if policy permits; default: allow but sanitized
                allow_external = True

        sanitized = _apply_redactions(text, redactions)

        # construct minimal reasons without exposing full matched secret in reasons
        safe_reasons = []
        for r in reasons:
            safe_reasons.append({
                "type": r["type"],
                "span": r["span"],
                "severity": r["severity"]
            })

        return {
            "allow_external": allow_external,
            "privacy_level": level,
            "sanitized": sanitized,
            "reasons": safe_reasons,
            "redactions": [{"start": r["start"], "end": r["end"], "replacement": r["replacement"]} for r in redactions],
            "version": self.version
        }
