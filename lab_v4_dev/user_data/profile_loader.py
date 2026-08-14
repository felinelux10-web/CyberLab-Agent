import json, os

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "user_profile.json")

def load_profile() -> dict:
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def get(key: str, default=None):
    return load_profile().get(key, default)
