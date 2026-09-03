"""Event types that drive Heddy's main loop.

Heddy is organised as a small state machine. Every stage of the pipeline
(listen for a keyword, record, transcribe, ask the assistant, speak the reply)
is represented by an :class:`ApplicationEvent`. A handler receives the event,
fills in ``result`` or ``error`` and marks it finished; the controller then
maps the finished event onto the next one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ApplicationEventType(Enum):
    """The stages of the voice pipeline."""

    EXIT = "exit"
    START = "start"
    SYNTHESIZE = "synthesize"
    PLAY = "play"
    LISTEN = "listen"
    START_RECORDING = "start_recording"
    USE_SNAPSHOT = "use_snapshot"
    STOP_RECORDING = "stop_recording"
    TRANSCRIBE = "transcribe"
    GET_SNAPSHOT = "get_snapshot"
    AI_INTERACT = "ai_interact"


class ProcessingStatus(Enum):
    INIT = "init"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ApplicationEvent:
    """A unit of work flowing through the controller.

    ``request`` is the handler's input and ``result`` its output. Handlers call
    :meth:`succeed` or :meth:`fail` rather than mutating the fields directly.
    """

    type: ApplicationEventType
    request: Any = None
    result: Any = None
    error: str | None = None
    status: ProcessingStatus = ProcessingStatus.INIT

    def succeed(self, result: Any = None) -> ApplicationEvent:
        """Mark the event as finished successfully, optionally with a result."""
        self.result = result
        self.error = None
        self.status = ProcessingStatus.SUCCESS
        return self

    def fail(self, error: str) -> ApplicationEvent:
        """Mark the event as failed with a human-readable reason."""
        self.error = error
        self.status = ProcessingStatus.ERROR
        return self

    @property
    def ok(self) -> bool:
        return self.status is ProcessingStatus.SUCCESS


@dataclass(frozen=True)
class AssistantRequest:
    """What the user asked, carried by an ``AI_INTERACT`` event.

    ``image_path`` is set when the user took a snapshot; the image is sent to
    the model alongside the transcribed question.
    """

    text: str
    image_path: Path | None = None
