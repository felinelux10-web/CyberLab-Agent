"""Project-scoped technical KnowledgeBase with explicit admission semantics."""
from __future__ import annotations
import json
import os
import re
import unicodedata
import secrets
from datetime import datetime
from lab_v4_dev.llm.provider_names import GROQ
KB_SCHEMA_VERSION = 2
DEFAULT_REVIEW_DAYS = 30
DEFAULT_ARCHIVE_DAYS = 90
BAD_PATTERNS = ["لا أستطيع التذكر", "لا أملك ذاكرة", "كمساعد ذكاء اصطناعي", "غير موجود في البيانات", "لا يوجد في البيانات", "لا أعرف", "I cannot", "as an AI"]
_STOP_WORDS = {"ما", "ماذا", "هل", "هو", "هي", "في", "عن", "من", "هذا", "هذه", "اشرح", "شرح", "لي", "the", "what", "is", "a", "an", "how"}

def _kb_path() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("knowledge_base/cyber_explain.json")

KB_PATH = os.path.expanduser("~/cyberlab_agent/workspace/knowledge_base/cyber_explain.json")

def _load() -> dict:
    path = _kb_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        return {"schema_version": KB_SCHEMA_VERSION, "records": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "records" not in data:
        records = {}
        for key, value in data.items():
            records[key] = dict(value) if isinstance(value, dict) else {"answer": str(value)}
        data = {"schema_version": KB_SCHEMA_VERSION, "records": records}
    data.setdefault("schema_version", KB_SCHEMA_VERSION)
    data.setdefault("records", {})
    return data

def _save(data: dict) -> None:
    path = _kb_path()
    from lab_v4_dev.core.safe_io import safe_write
    result = safe_write(
        path,
        json.dumps(data, indent=2, ensure_ascii=False),
        reason="knowledge_base:save",
    )
    if result.get("status") != "success":
        raise PermissionError(result.get("message", "تعذر حفظ قاعدة المعرفة"))

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    text = re.sub(r"[\u064B-\u065F]", "", text)
    text = re.sub(r"[؟?!،؛:.,()\[\]{}\"']", " ", text)
    return " ".join(text.split())

def _concept_key(text: str) -> str:
    normalized = _normalize(text)
    tokens = [token for token in normalized.split() if token not in _STOP_WORDS]
    if "tcp" in tokens and any(
        marker in normalized
        for marker in ("handshake", "three-way", "مصافحة", "المصافحة", "إنشاء اتصال")
    ):
        return "net tcp three way handshake"
    return " ".join(tokens)

def _record_matches(record: dict, key: str) -> bool:
    if record.get("canonical_key") == key:
        return True
    aliases = {_concept_key(alias) for alias in record.get("aliases", [])}
    if key in aliases:
        return True
    left, right = set(key.split()), set(record.get("canonical_key", "").split())
    return bool(left and right and len(left & right) / max(len(left), len(right)) >= 0.8)

def search(topic: str) -> str | None:
    from lab_v4_dev.memory.intelligence import rank_memory_records
    key = _concept_key(topic)
    if not key: return None
    data = _load()
    candidates = []
    for storage_key, record in data.get("records", {}).items():
        if not isinstance(record, dict): continue
        ranked = rank_memory_records(topic, [record], fields=("canonical_key","aliases","concept_id"))
        score = ranked[0]["match_score"] if ranked else 0.0
        if _record_matches(record, key): score = max(score, 0.85)
        if score >= 0.42: candidates.append((score, storage_key, record))
    candidates.sort(key=lambda item: (item[0], float(item[2].get("importance", 0.0) or 0.0),
        str(item[2].get("updated_at") or ""),
        int(item[2].get("access_count", item[2].get("hits", 0)) or 0)), reverse=True)
    for _, _, record in candidates:
        if record.get("status", "ACTIVE") == "ARCHIVED": continue
        record["hits"] = int(record.get("hits", record.get("access_count", 0))) + 1
        record["access_count"] = record["hits"]
        record["last_accessed_at"] = datetime.now().isoformat()
        _save(data)
        return record.get("answer")
    if any(record.get("status") == "ARCHIVED" for _, _, record in candidates) and restore(topic):
        return search(topic)
    return None

def is_quality(answer: str, topic: str = "") -> bool:
    answer = str(answer or "")
    if len(answer) < 100 or any(p.casefold() in answer.casefold() for p in BAD_PATTERNS):
        return False
    return bool(_concept_key(topic))

def store(topic: str, answer: str, source: str = GROQ, *, confirmed: bool = False, scope: str = "technical", confidence: str = "OBSERVED", importance: float = 0.5):
    """Admit a technical record only after quality or explicit confirmation."""
    if not confirmed and not is_quality(answer, topic):
        return False
    key = _concept_key(topic)
    if not key:
        return False
    data = _load()
    records = data.setdefault("records", {})
    now = datetime.now().isoformat()
    existing_key = next((k for k, record in records.items() if _record_matches(record, key)), None)
    if existing_key is not None:
        record = records[existing_key]
        record.setdefault("aliases", []).append(str(topic))
        record["aliases"] = list(dict.fromkeys(record["aliases"]))[-20:]
        record.update({"answer": answer, "updated_at": now, "status": "ACTIVE", "source": source, "confidence": confidence})
        record["importance"] = max(float(record.get("importance", 0.0)), float(importance))
    else:
        from lab_v4_dev.memory.intelligence import memory_metadata
        metadata = memory_metadata("technical_knowledge", source=source,
            confidence=confidence, importance=importance, scope=scope)
        records[key] = {
            **metadata,
            "memory_id": f"kb:{secrets.token_hex(8)}", "concept_id": f"TECH.{key.replace(' ', '.')}", "canonical_key": key,
            "aliases": [str(topic)], "answer": answer, "source": source, "scope": scope,
            "confidence": confidence, "quality": "validated" if is_quality(answer, topic) else "explicitly_confirmed",
            "importance": float(importance), "created_at": now, "updated_at": now,
            "last_accessed_at": None, "access_count": 0, "hits": 0, "status": "ACTIVE", "relationships": [],
        }
    _save(data)
    return True

def hit(topic: str):
    return search(topic)


def review_lifecycle(*, now=None, review_days: int = DEFAULT_REVIEW_DAYS, archive_days: int = DEFAULT_ARCHIVE_DAYS) -> dict:
    """Review age/usage/importance; never archive critical or frequently used records."""
    from datetime import datetime, timedelta
    now = now or datetime.now()
    data = _load()
    reviewed = {"active": 0, "warm": 0, "cold": 0, "archived": 0}
    for record in data.get("records", {}).values():
        if record.get("status") == "ARCHIVED":
            reviewed["archived"] += 1
            continue
        updated = record.get("updated_at") or record.get("created_at")
        try:
            age = now - datetime.fromisoformat(updated).replace(tzinfo=None)
        except (TypeError, ValueError):
            age = timedelta(0)
        important = float(record.get("importance", 0.0)) >= 0.8
        hits = int(record.get("access_count", record.get("hits", 0)))
        if important or hits >= 3 or age < timedelta(days=review_days):
            record["status"] = "ACTIVE"
            reviewed["active"] += 1
        elif age >= timedelta(days=archive_days) and hits == 0:
            record["status"] = "ARCHIVED"
            record["archive_reference"] = record.get("memory_id")
            reviewed["archived"] += 1
        else:
            record["status"] = "WARM" if hits else "COLD"
            reviewed[record["status"].lower()] += 1
    _save(data)
    return reviewed


def restore(topic: str) -> bool:
    """Restore an archived record to WARM on explicit retrieval."""
    key = _concept_key(topic)
    data = _load()
    for record in data.get("records", {}).values():
        if _record_matches(record, key) and record.get("status") == "ARCHIVED":
            record["status"] = "WARM"
            record["updated_at"] = datetime.now().isoformat()
            _save(data)
            return True
    return False
