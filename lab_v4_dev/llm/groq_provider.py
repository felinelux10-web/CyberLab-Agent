"""
Groq Provider Plugin
v5.9.13-dev
"""

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.llm.groq_client import ask as groq_ask


class GroqProvider(BaseProvider):

    def ask(
        self,
        prompt,
        system=None,
        max_tokens=800,
        model=None,
        temperature=0.3,
    ):
        return groq_ask(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            model=model,
            temperature=temperature,
        )


provider = GroqProvider()
