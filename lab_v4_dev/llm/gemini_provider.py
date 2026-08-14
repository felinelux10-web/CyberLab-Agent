"""
Gemini Provider
H.8.6.x
REST API implementation
"""

import requests

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.config.provider_config import get_provider_config


class GeminiProvider(BaseProvider):

    def ask(
        self,
        prompt,
        system=None,
        max_tokens=800,
        model=None,
        temperature=0.3,
    ):

        cfg = get_provider_config("gemini")

        api_key = cfg.get("api_key", "")
        model_name = model or cfg.get("model", "gemini-2.5-flash")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + model_name
            + ":generateContent?key="
            + api_key
        )

        text_prompt = ((system + "\n\n") if system else "") + prompt

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": text_prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        try:

            r = requests.post(
                url,
                json=payload,
                timeout=30
            )

            data = r.json()

            if r.status_code != 200:
                return {
                    "status": "error",
                    "provider": "gemini",
                    "message": data
                }

            text = data["candidates"][0]["content"]["parts"][0]["text"]

            return {
                "status": "success",
                "text": text,
                "model": model_name,
                "provider": "gemini"
            }

        except Exception as e:

            return {
                "status": "error",
                "provider": "gemini",
                "message": str(e)
            }


provider = GeminiProvider()
