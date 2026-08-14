# CyberLab Agent v4.6
# lab_v4/llm/groq_client.py

import os
import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"
ENV_FILE     = "lab_v4/configs/.env"

def _load_key() -> str:
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith("GROQ_API_KEY="):
                    return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY", "")

def ask(prompt: str, system: str = None, max_tokens: int = 500) -> dict:
    key = _load_key()
    if not key:
        return {"status": "error", "message": "GROQ_API_KEY not found"}

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        r = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type" : "application/json",
            },
            json={
                "model"     : GROQ_MODEL,
                "messages"  : messages,
                "max_tokens": max_tokens,
            },
            timeout=30
        )

        if r.status_code == 200:
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            return {
                "status": "success",
                "text"  : text,
                "model" : GROQ_MODEL,
                "tokens": data.get("usage", {}).get("total_tokens", 0),
            }
        else:
            return {
                "status" : "error",
                "message": f"HTTP {r.status_code}: {r.text[:200]}",
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}
