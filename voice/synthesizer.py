"""Text-to-speech interface."""
from abc import ABC, abstractmethod


class BaseSynthesizer(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        ...
