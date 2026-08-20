"""
P08 — Dummy Provider.

Explicit fallback provider. Never masquerades as normal provider success.
"""

from lab_v4_dev.llm.base_provider import BaseProvider
from lab_v4_dev.llm.contracts import LLMRequest, LLMResponse


class DummyProvider(BaseProvider):

    @property
    def name(self) -> str:
        return "dummy"

    def execute(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse.fallback(
            text="[Dummy Provider - fallback] " + (request.prompt or ""),
            provider=self.name,
            model="dummy",
        )


provider = DummyProvider()
