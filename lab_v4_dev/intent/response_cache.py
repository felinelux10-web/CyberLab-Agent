# CyberLab Agent v5.9.7.J
# intent/response_cache.py
import json, os

def _cache_path() -> str:
    from lab_v4_dev.core.project_context import project_data_file
    return project_data_file("response_cache.json")

# سياسة الـ Cache لكل intent
CACHE_POLICY = {
    "cyber_explain" : {"enabled": True,  "ttl_days": 30},
    "health"        : {"enabled": True,  "ttl_days": 0},
    "self_diagnose" : {"enabled": True,  "ttl_days": 0},
    "project_scan"  : {"enabled": False},
    "file_impact"   : {"enabled": False},
    "analyze_code"  : {"enabled": False},
    "impact_chain"  : {"enabled": False},
}

# رفض الردود الفاسدة
REJECT_PATTERNS = [
    "الجواب:",
    "لا أعرف",
    "غير موجود",
    "لا يوجد معلومات",
    "لا استطيع",
]

MIN_LENGTH = 30

def should_save(intent: str, text: str) -> bool:
    policy = CACHE_POLICY.get(intent, {"enabled": True})
    if not policy.get("enabled", True):
        return False
    if not text or len(text.strip()) < MIN_LENGTH:
        return False
    for pattern in REJECT_PATTERNS:
        if pattern in text:
            return False
    return True

def _load():
    path = _cache_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def _save(data):
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get(intent, target=""):
    policy = CACHE_POLICY.get(intent, {"enabled": True})
    if not policy.get("enabled", True):
        return None
    return _load().get(intent, {}).get(target or "", None)

def save(intent, target, text):
    if not should_save(intent, text):
        return
    data = _load()
    if intent not in data: data[intent] = {}
    data[intent][target or ""] = text
    _save(data)

def clear(intent=None, target=None):
    data = _load()
    if intent is None: _save({})
    elif target is None: data.pop(intent, None); _save(data)
    else: data.get(intent, {}).pop(target or "", None); _save(data)
