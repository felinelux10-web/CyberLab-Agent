"""
Base Provider Interface
v5.9.13-dev
"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):

    @abstractmethod
    def ask(
        self,
        prompt: str,
        system: str = None,
        max_tokens: int = 800,
        model: str = None,
        temperature: float = 0.3,
    ):
        pass
