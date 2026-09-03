"""The main loop: a state machine that ties the pipeline stages together.

The controller knows nothing about PyAudio, OpenAI or any other provider. It
receives the components through its constructor (see :mod:`heddy.app` for the
wiring) and only speaks in :class:`~heddy.events.ApplicationEvent` objects,
which keeps the whole interaction flow testable without a microphone.

A typical interaction::

    "computer"  -> start recording
    "snapshot"  -> take a webcam picture (while recording)
    "reply"     -> stop recording, transcribe, ask the assistant, speak the answer
"""

from __future__ import annotations

import contextlib
import logging
from typing import Protocol

from heddy.events import (
    ApplicationEvent,
    ApplicationEventType,
    AssistantRequest,
    ProcessingStatus,
)
from heddy.exceptions import HeddyError
from heddy.resources import (
    LISTENING_SOUND,
    RESPOND_SOUND,
    SNAPSHOT_SOUND,
    START_RECORDING_SOUND,
)

log = logging.getLogger(__name__)

WAKE_WORD = "computer"
SNAPSHOT_WORD = "snapshot"
REPLY_WORD = "reply"
DEFAULT_GREETING = "Hello! How can I assist you today?"


class EventHandler(Protocol):
    def __call__(self, event: ApplicationEvent) -> ApplicationEvent: ...


class Assistant(Protocol):
    def handle(self, event: ApplicationEvent) -> ApplicationEvent: ...


class Transcriber(Protocol):
    def transcribe(self, event: ApplicationEvent) -> ApplicationEvent: ...


class Synthesizer(Protocol):
    def synthesize(self, event: ApplicationEvent) -> ApplicationEvent: ...


class Player(Protocol):
    def play(self, event: ApplicationEvent) -> ApplicationEvent: ...
    def play_sound(self, name: str) -> None: ...
    def close(self) -> None: ...


class Recorder(Protocol):
    @property
    def is_recording(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> object: ...


class Camera(Protocol):
    def capture_async(self) -> None: ...
    def attach_snapshot(self, event: ApplicationEvent) -> ApplicationEvent: ...


class KeywordDetector(Protocol):
    def listen(self, event: ApplicationEvent) -> ApplicationEvent: ...
    def clear(self) -> None: ...


class MainController:
    def __init__(
        self,
        *,
        assistant: Assistant,
        transcriber: Transcriber,
        synthesizer: Synthesizer,
        audio_player: Player,
        recorder: Recorder,
        camera: Camera,
        keyword_detector: KeywordDetector,
        greeting: str = DEFAULT_GREETING,
    ) -> None:
        self.assistant = assistant
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.audio_player = audio_player
        self.recorder = recorder
        self.camera = camera
        self.keyword_detector = keyword_detector
        self.greeting = greeting
        self.is_recording = False
        self.picture_mode = False

    # -- dispatch -----------------------------------------------------------------

    def process_event(self, event: ApplicationEvent) -> ApplicationEvent:
        """Run the handler for ``event``.

        Returns either the same event, finished by its handler, or a brand-new
        pending event when the stage needs no external work.
        """
        kind = event.type
        if kind is ApplicationEventType.START:
            self.audio_player.play_sound(LISTENING_SOUND)
            return ApplicationEvent(ApplicationEventType.SYNTHESIZE, request=self.greeting)
        if kind is ApplicationEventType.SYNTHESIZE:
            return self.synthesizer.synthesize(event)
        if kind is ApplicationEventType.PLAY:
            return self.audio_player.play(event)
        if kind is ApplicationEventType.LISTEN:
            return self.keyword_detector.listen(event)
        if kind is ApplicationEventType.START_RECORDING:
            self.audio_player.play_sound(START_RECORDING_SOUND)
            self.recorder.start()
            self.is_recording = True
            return ApplicationEvent(ApplicationEventType.LISTEN)
        if kind is ApplicationEventType.USE_SNAPSHOT:
            self.audio_player.play_sound(SNAPSHOT_SOUND)
            self.picture_mode = True
            self.camera.capture_async()
            return ApplicationEvent(ApplicationEventType.LISTEN)
        if kind is ApplicationEventType.STOP_RECORDING:
            self.audio_player.play_sound(RESPOND_SOUND)
            recording = self.recorder.stop()
            self.is_recording = False
            self.keyword_detector.clear()
            return ApplicationEvent(ApplicationEventType.TRANSCRIBE, request=recording)
        if kind is ApplicationEventType.TRANSCRIBE:
            return self.transcriber.transcribe(event)
        if kind is ApplicationEventType.GET_SNAPSHOT:
            return self.camera.attach_snapshot(event)
        if kind is ApplicationEventType.AI_INTERACT:
            return self.assistant.handle(event)
        raise ValueError(f"No handler for event type {kind}")

    def process_result(self, event: ApplicationEvent) -> ApplicationEvent:
        """Decide what happens after ``event`` has been processed."""
        if event.status is ProcessingStatus.ERROR:
            return self._recover(event)
        if event.status is ProcessingStatus.INIT:
            return event  # a fresh event produced by process_event; run it next

        kind = event.type
        if kind is ApplicationEventType.SYNTHESIZE:
            return ApplicationEvent(ApplicationEventType.PLAY, request=event.result)
        if kind is ApplicationEventType.PLAY:
            return ApplicationEvent(ApplicationEventType.LISTEN)
        if kind is ApplicationEventType.LISTEN:
            return self.handle_keyword(str(event.result))
        if kind is ApplicationEventType.TRANSCRIBE:
            log.info("Transcript: %r", event.result)
            if self.picture_mode:
                return ApplicationEvent(ApplicationEventType.GET_SNAPSHOT, request=event.result)
            return ApplicationEvent(
                ApplicationEventType.AI_INTERACT, request=AssistantRequest(text=event.result)
            )
        if kind is ApplicationEventType.GET_SNAPSHOT:
            self.picture_mode = False
            return ApplicationEvent(ApplicationEventType.AI_INTERACT, request=event.result)
        if kind is ApplicationEventType.AI_INTERACT:
            log.info("Assistant: %r", event.result)
            return ApplicationEvent(ApplicationEventType.SYNTHESIZE, request=event.result)
        raise ValueError(f"No result handling for event type {kind}")

    def handle_keyword(self, word: str) -> ApplicationEvent:
        """Map a detected keyword to the next event, given the current state."""
        word = word.lower().strip()
        if WAKE_WORD in word and not self.is_recording:
            return ApplicationEvent(ApplicationEventType.START_RECORDING)
        if SNAPSHOT_WORD in word and self.is_recording and not self.picture_mode:
            return ApplicationEvent(ApplicationEventType.USE_SNAPSHOT)
        if REPLY_WORD in word and self.is_recording:
            return ApplicationEvent(ApplicationEventType.STOP_RECORDING)
        return ApplicationEvent(ApplicationEventType.LISTEN)

    # -- running ------------------------------------------------------------------

    def step(self, event: ApplicationEvent) -> ApplicationEvent:
        """Process one event and return the next one."""
        log.debug("Event: %s", event.type.value)
        try:
            result = self.process_event(event)
        except HeddyError as exc:
            result = event.fail(str(exc))
        return self.process_result(result)

    def run(self, event: ApplicationEvent | None = None) -> None:
        """Run the loop until an ``EXIT`` event or Ctrl+C."""
        current = event or ApplicationEvent(ApplicationEventType.START)
        try:
            while current.type is not ApplicationEventType.EXIT:
                current = self.step(current)
        except KeyboardInterrupt:
            log.info("Shutting down")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self.recorder.is_recording:
            with contextlib.suppress(HeddyError):
                self.recorder.stop()
        self.audio_player.close()

    def _recover(self, event: ApplicationEvent) -> ApplicationEvent:
        """Log a failed stage, drop any half-finished interaction, and listen again."""
        log.error("%s failed: %s", event.type.value, event.error)
        if self.is_recording:
            try:
                self.recorder.stop()
            except HeddyError as exc:
                log.error("%s", exc)
            self.is_recording = False
        self.picture_mode = False
        self.keyword_detector.clear()
        return ApplicationEvent(ApplicationEventType.LISTEN)
