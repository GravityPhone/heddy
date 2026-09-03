"""Provider-agnostic text-to-speech types and the pipeline adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from heddy.audio.pcm import PcmAudio
from heddy.events import ApplicationEvent


class TTSStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True)
class TTSResult:
    status: TTSStatus
    audio: PcmAudio | None = None
    error: str | None = None

    @classmethod
    def ok(cls, audio: PcmAudio) -> TTSResult:
        return cls(TTSStatus.SUCCESS, audio=audio)

    @classmethod
    def failed(cls, error: str) -> TTSResult:
        return cls(TTSStatus.ERROR, error=error)


class Synthesizer(Protocol):
    """Anything that can turn text into playable PCM audio."""

    def synthesize(self, text: str) -> TTSResult: ...


class TTSManager:
    """Adapts a :class:`Synthesizer` to ``SYNTHESIZE`` events."""

    def __init__(self, synthesizer: Synthesizer) -> None:
        self.synthesizer = synthesizer

    def synthesize(self, event: ApplicationEvent) -> ApplicationEvent:
        """``event.request`` is the text to speak; the result is :class:`PcmAudio`."""
        result = self.synthesizer.synthesize(str(event.request))
        if result.status is TTSStatus.SUCCESS:
            return event.succeed(result.audio)
        return event.fail(result.error or "Speech synthesis failed.")
