"""Provider-agnostic speech-to-text types and the pipeline adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from heddy.events import ApplicationEvent


class STTStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True)
class STTResult:
    status: STTStatus
    text: str | None = None
    error: str | None = None

    @classmethod
    def ok(cls, text: str) -> STTResult:
        return cls(STTStatus.SUCCESS, text=text)

    @classmethod
    def failed(cls, error: str) -> STTResult:
        return cls(STTStatus.ERROR, error=error)


class Transcriber(Protocol):
    """Anything that can turn an audio file into text."""

    def transcribe_file(self, path: Path) -> STTResult: ...


class STTManager:
    """Adapts a :class:`Transcriber` to ``TRANSCRIBE`` events."""

    def __init__(self, transcriber: Transcriber) -> None:
        self.transcriber = transcriber

    def transcribe(self, event: ApplicationEvent) -> ApplicationEvent:
        """``event.request`` is the path of a WAV file; the result is its transcript."""
        result = self.transcriber.transcribe_file(Path(event.request))
        if result.status is STTStatus.SUCCESS:
            return event.succeed(result.text)
        return event.fail(result.error or "Transcription failed.")
