"""Shared fakes for the pipeline components, so tests never touch hardware or the network."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from heddy.audio.pcm import PcmAudio
from heddy.controller import MainController
from heddy.events import ApplicationEvent, AssistantRequest


class FakePlayer:
    def __init__(self) -> None:
        self.sounds: list[str] = []
        self.played: list[PcmAudio] = []
        self.closed = False
        self.error: str | None = None

    def play_sound(self, name: str) -> None:
        self.sounds.append(name)

    def play(self, event: ApplicationEvent) -> ApplicationEvent:
        if self.error:
            return event.fail(self.error)
        self.played.append(event.request)
        return event.succeed()

    def close(self) -> None:
        self.closed = True


class FakeRecorder:
    def __init__(self, path: Path = Path("/tmp/heddy-test-recording.wav")) -> None:
        self.path = path
        self.is_recording = False
        self.starts = 0
        self.stops = 0
        self.stop_error: Exception | None = None

    def start(self) -> None:
        self.is_recording = True
        self.starts += 1

    def stop(self) -> Path:
        self.is_recording = False
        self.stops += 1
        if self.stop_error is not None:
            raise self.stop_error
        return self.path


class FakeCamera:
    def __init__(self, image_path: Path | None = Path("/tmp/heddy-test-snapshot.png")) -> None:
        self.image_path = image_path
        self.captures = 0

    def capture_async(self) -> None:
        self.captures += 1

    def attach_snapshot(self, event: ApplicationEvent) -> ApplicationEvent:
        return event.succeed(AssistantRequest(text=str(event.request), image_path=self.image_path))


class FakeDetector:
    def __init__(self, words: list[str] | None = None) -> None:
        self.words = list(words or [])
        self.cleared = 0
        self.listens = 0

    def listen(self, event: ApplicationEvent) -> ApplicationEvent:
        self.listens += 1
        if not self.words:
            raise KeyboardInterrupt  # end the run() loop once the script is exhausted
        return event.succeed(self.words.pop(0))

    def clear(self) -> None:
        self.cleared += 1


class FakeTranscriber:
    def __init__(self, text: str = "what time is it") -> None:
        self.text = text
        self.error: str | None = None
        self.requests: list[object] = []

    def transcribe(self, event: ApplicationEvent) -> ApplicationEvent:
        self.requests.append(event.request)
        if self.error:
            return event.fail(self.error)
        return event.succeed(self.text)


class FakeSynthesizer:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.error: str | None = None

    def synthesize(self, event: ApplicationEvent) -> ApplicationEvent:
        self.texts.append(str(event.request))
        if self.error:
            return event.fail(self.error)
        return event.succeed(PcmAudio(b"\x00\x00" * 240, sample_rate=24000))


class FakeAssistant:
    def __init__(self, reply: str = "It is noon.") -> None:
        self.reply = reply
        self.error: str | None = None
        self.requests: list[AssistantRequest] = []

    def handle(self, event: ApplicationEvent) -> ApplicationEvent:
        self.requests.append(event.request)
        if self.error:
            return event.fail(self.error)
        return event.succeed(self.reply)


@dataclass
class Fakes:
    player: FakePlayer = field(default_factory=FakePlayer)
    recorder: FakeRecorder = field(default_factory=FakeRecorder)
    camera: FakeCamera = field(default_factory=FakeCamera)
    detector: FakeDetector = field(default_factory=FakeDetector)
    transcriber: FakeTranscriber = field(default_factory=FakeTranscriber)
    synthesizer: FakeSynthesizer = field(default_factory=FakeSynthesizer)
    assistant: FakeAssistant = field(default_factory=FakeAssistant)

    def controller(self) -> MainController:
        return MainController(
            assistant=self.assistant,
            transcriber=self.transcriber,
            synthesizer=self.synthesizer,
            audio_player=self.player,
            recorder=self.recorder,
            camera=self.camera,
            keyword_detector=self.detector,
        )


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()
