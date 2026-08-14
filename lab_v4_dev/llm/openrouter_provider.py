"""
OpenRouter Provider
H.8.6.x
REST API implementation
"""

import requests

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.config.provider_config import get_provider_config


class OpenRouterProvider(BaseProvider):

    def ask(
        self,
        prompt,
        system=None,
        max_tokens=800,
        model=None,
        temperature=0.3,
    ):

        cfg = get_provider_config("openrouter")

        api_key = cfg.get("api_key","")
        model_name = model or cfg.get("model")
        url = cfg.get("base_url")

        messages = []

        if system:
            messages.append({
                "role":"system",
                "content":system
            })

        messages.append({
            "role":"user",
            "content":prompt
        })

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:

            r = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            data = r.json()

            if r.status_code != 200:
                return {
                    "status":"error",
                    "provider":"openrouter",
                    "message":data
                }

            text = data["choices"][0]["message"]["content"]

            return {
                "status":"success",
                "text":text,
                "model":model_name,
                "provider":"openrouter"
            }

        except Exception as e:
            return {
                "status":"error",
                "provider":"openrouter",
                "message":str(e)
            }


provider = OpenRouterProvider()
