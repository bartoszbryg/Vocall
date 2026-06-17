"""Speech-to-text interface. Concrete implementations swap here."""
from abc import ABC, abstractmethod


class BaseTranscriber(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        ...
