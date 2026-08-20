"""
P08 — Canonical Provider Interface.

The interface is intentionally compatible with legacy provider
implementations during the migration phase.
"""

from abc import ABC

from lab_v4_dev.llm.contracts import LLMRequest, LLMResponse


class BaseProvider(ABC):
    """
    Canonical provider boundary.

    Legacy providers may continue implementing ask() until their
    execution path is migrated to execute(LLMRequest).
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def execute(self, request: LLMRequest) -> LLMResponse:
        """
        Canonical execution entry point.

        Legacy implementations are adapted through ask().
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement execute() "
            "or be wrapped by LegacyProviderAdapter"
        )

    def ask(
        self,
        prompt,
        system=None,
        max_tokens=800,
        model=None,
        temperature=0.3,
    ) -> LLMResponse:
        """
        Legacy compatibility entry point.

        New Gateway code will use execute(LLMRequest).
        """
        request = LLMRequest(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            model=model,
            temperature=temperature,
        )

        return self.execute(request)
