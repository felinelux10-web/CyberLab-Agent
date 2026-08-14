"""
Intent Cache — v5.9.3
يحفظ الجمل التي فهمها Groq ويسترجعها محلياً في المرات القادمة.
"""
import json, os

CACHE_FILE = os.path.expanduser(
    "~/cyberlab_agent/project_data/intent_cache.json"
)

def _load() -> dict:
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(cache: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def get(text: str) -> str | None:
    """ابحث عن intent محفوظ لهذه الجملة. يعيد None إذا لم يوجد."""
    return _load().get(text.strip())

def save(text: str, intent: str):
    """احفظ intent لهذه الجملة للاستخدام لاحقاً."""
    cache = _load()
    cache[text.strip()] = intent
    _save(cache)
