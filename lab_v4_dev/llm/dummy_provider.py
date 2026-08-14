"""
Dummy Provider
Marked fallback provider. Must never masquerade as a real provider success.
"""

from lab_v4_dev.llm.base_provider import BaseProvider


class DummyProvider(BaseProvider):

    def ask(
        self,
        prompt,
        system=None,
        max_tokens=800,
        model=None,
        temperature=0.3,
    ):
        return {
            "status": "fallback",
            "is_dummy": True,
            "fallback_used": True,
            "text": "[Dummy Provider - fallback] " + (prompt or ""),
            "model": "dummy",
            "tokens": 0,
        }


provider = DummyProvider()
