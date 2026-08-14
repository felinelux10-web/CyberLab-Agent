import json
from pathlib import Path

CONFIG_PATH = Path("lab_v4_dev/config/llm_provider.json")


def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("LLM provider config not found")

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_active_provider():
    cfg = load_config()
    return cfg.get("active_provider", "groq")


def get_fallback_provider():
    cfg = load_config()
    return cfg.get("fallback_provider", "local")


def get_timeout():
    cfg = load_config()
    return int(cfg.get("timeout_ms", 8000))


def is_provider_enabled(name: str) -> bool:
    cfg = load_config()
    providers = cfg.get("providers", {})
    return providers.get(name, {}).get("enabled", False)


def get_provider_config(name: str) -> dict:
    cfg = load_config()
    providers = cfg.get("providers", {})
    return providers.get(name, {})
