"""Shared intelligence primitives for CyberLab Agent memory stores.

Safe persistence, normalized matching, relevance scoring, and provenance metadata.
This module does not own memory domains or authorize cross-domain reads.
"""
from __future__ import annotations
import json, os, re, secrets, unicodedata
from datetime import datetime
from typing import Iterable

MEMORY_RECORD_VERSION = 1
DEFAULT_STOP_WORDS = {
    "ما","ماذا","هل","هو","هي","في","عن","من","هذا","هذه","ذلك","تلك",
    "الى","إلى","على","مع","ثم","او","أو","و","لي","عند","عندي","لك",
    "كل","جميع","جلسة","الجلسة","جلسه","الجلسه","المحفوظة","المحفوظ",
    "اريد","أريد","اكتب","اعرض","ملخص","ملخصات","لخص","تلخيص","the",
    "what","how","is","a","an","in","on","for","of","to","and",
}

def now_iso() -> str:
    return datetime.now().astimezone().isoformat()

def normalize_memory_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = (text.replace("أ","ا").replace("إ","ا").replace("آ","ا")
            .replace("ى","ي").replace("ؤ","و").replace("ئ","ي").replace("ـ",""))
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())

def memory_tokens(value: object) -> set[str]:
    return {token for token in normalize_memory_text(value).split()
            if len(token) > 1 and token not in DEFAULT_STOP_WORDS}

def score_memory_record(query: object, record: dict, *,
                        fields: Iterable[str] = ("title","topic","summary","content")) -> float:
    query_norm, query_tokens = normalize_memory_text(query), memory_tokens(query)
    if not query_norm or not query_tokens or not isinstance(record, dict):
        return 0.0
    best = 0.0
    for field in fields:
        value = record.get(field)
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for candidate in values:
            candidate_norm, tokens = normalize_memory_text(candidate), memory_tokens(candidate)
            if not candidate_norm or not tokens:
                continue
            overlap = len(query_tokens & tokens)
            precision, recall = overlap / len(query_tokens), overlap / len(tokens)
            score = (2 * precision * recall / (precision + recall) * 0.72) if precision + recall else 0.0
            if query_norm == candidate_norm: score += 0.32
            elif len(query_norm) >= 5 and query_norm in candidate_norm: score += 0.22
            elif len(candidate_norm) >= 5 and candidate_norm in query_norm: score += 0.16
            best = max(best, min(score, 1.0))
    if best:
        confidence = str(record.get("confidence") or record.get("quality") or "").casefold()
        if confidence in {"explicit","explicitly_confirmed","test_verified","runtime_verified"}: best += 0.035
        elif confidence in {"inferred","observed","historical"}: best += 0.01
        try: best += max(0.0, min(1.0, float(record.get("importance", 0.0)))) * 0.02
        except (TypeError, ValueError): pass
    return round(min(best, 1.0), 6)

def rank_memory_records(query: object, records: Iterable[dict], *,
                        fields: Iterable[str] = ("title","topic","summary","content"),
                        limit: int | None = None, minimum_score: float = 0.0) -> list[dict]:
    ranked = []
    for record in records:
        if not isinstance(record, dict): continue
        score = score_memory_record(query, record, fields=fields)
        if score < minimum_score: continue
        item = dict(record); item["match_score"] = score; ranked.append(item)
    def safe_int(value):
        try: return int(value or 0)
        except (TypeError, ValueError): return 0
    ranked.sort(key=lambda item: (item["match_score"],
        str(item.get("updated_at") or item.get("timestamp") or item.get("created_at") or ""),
        safe_int(item.get("access_count", item.get("hits", 0)))), reverse=True)
    return ranked if limit is None else ranked[:max(0, int(limit))]

def memory_metadata(memory_type: str, *, source: str, confidence: str = "observed",
                    importance: float = 0.5, scope: str = "project") -> dict:
    try: importance = max(0.0, min(1.0, float(importance)))
    except (TypeError, ValueError): importance = 0.5
    now = now_iso()
    return {"record_version": MEMORY_RECORD_VERSION, "memory_type": str(memory_type),
            "scope": str(scope), "source": str(source), "confidence": str(confidence),
            "importance": importance, "created_at": now, "updated_at": now,
            "last_accessed_at": None, "access_count": 0, "status": "ACTIVE"}

def atomic_write_json(path: str, data: object, *, mode: int | None = None) -> None:
    """Durably replace a JSON file without exposing a partial document."""
    target = os.path.abspath(os.path.expanduser(str(path)))
    directory = os.path.dirname(target)
    os.makedirs(directory, mode=0o700 if mode == 0o600 else 0o755, exist_ok=True)
    temporary = os.path.join(directory, f".{os.path.basename(target)}.{secrets.token_hex(6)}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                             mode if mode is not None else 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            if mode is not None:
                try: os.chmod(temporary, mode)
                except OSError: pass
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(directory, os.O_RDONLY)
            try: os.fsync(directory_fd)
            finally: os.close(directory_fd)
        except OSError: pass
    except Exception:
        try: os.unlink(temporary)
        except OSError: pass
        raise
