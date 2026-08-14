"""
Knowledge Base - v5.9.1-B
بسيط: exact match فقط، بدون embeddings أو similarity
"""
from lab_v4_dev.llm.provider_names import GROQ
import os
import json
from datetime import datetime

KB_PATH = os.path.expanduser(
    "~/cyberlab_agent/workspace/knowledge_base/cyber_explain.json"
)

def _load():
    os.makedirs(os.path.dirname(KB_PATH), exist_ok=True)
    if not os.path.exists(KB_PATH):
        return {}
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data):
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _normalize(text):
    return text.strip().lower()

def search(topic: str) -> str | None:
    key = _normalize(topic)
    data = _load()
    entry = data.get(key)
    if entry:
        return entry["answer"]
    return None

BAD_PATTERNS = [
    "لا أستطيع التذكر",
    "لا أملك ذاكرة",
    "كمساعد ذكاء اصطناعي",
    "غير موجود في البيانات",
    "لا يوجد في البيانات",
    "لا أعرف",
    "I cannot",
    "as an AI",
]

def is_quality(answer: str, topic: str = "") -> bool:
    """يتحقق أن الإجابة تستحق الحفظ"""
    if len(answer) < 100:
        return False
    for pattern in BAD_PATTERNS:
        if pattern in answer:
            return False
    # رفض المصطلحات القصيرة جداً (أقل من 3 أحرف)
    if topic:
        words = topic.strip().split()
        last_word = words[-1] if words else ""
        if len(last_word) < 3:
            return False
    return True

def store(topic: str, answer: str, source: str = GROQ):
    if not is_quality(answer, topic):
        return False
    key = _normalize(topic)
    data = _load()
    if key not in data:
        data[key] = {
            "answer": answer,
            "source": source,
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "hits": 0,
        }
    else:
        data[key]["hits"] = data[key].get("hits", 0) + 1
    _save(data)

def hit(topic: str):
    key = _normalize(topic)
    data = _load()
    if key in data:
        data[key]["hits"] = data[key].get("hits", 0) + 1
        _save(data)
