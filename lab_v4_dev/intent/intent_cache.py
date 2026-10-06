"""
Intent Cache — v5.9.3
يحفظ الجمل التي فهمها Groq ويسترجعها محلياً في المرات القادمة.
"""
import json, os

def _cache_file() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("intent_cache.json")

def _load() -> dict:
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(cache: dict):
    path = _cache_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def get(text: str) -> str | None:
    """ابحث عن intent محفوظ لهذه الجملة. يعيد None إذا لم يوجد."""
    return _load().get(text.strip())

def save(text: str, intent: str):
    """احفظ intent لهذه الجملة للاستخدام لاحقاً."""
    cache = _load()
    cache[text.strip()] = intent
    _save(cache)
