"""Audio output: bundled sound effects and synthesized speech."""

from __future__ import annotations

import logging
import wave
from collections.abc import Iterable

import pyaudio

from heddy.audio.pcm import PcmAudio
from heddy.audio.quiet import suppress_stderr
from heddy.events import ApplicationEvent
from heddy.resources import sound_path

log = logging.getLogger(__name__)


class AudioPlayer:
    """Plays WAV sound effects and raw PCM speech through the default output device."""

    def __init__(self, chunk_frames: int = 1024) -> None:
        self._chunk_frames = chunk_frames
        with suppress_stderr():
            self._pyaudio = pyaudio.PyAudio()

    def play_sound(self, name: str) -> None:
        """Play one of the bundled sound effects (see :mod:`heddy.resources`)."""
        with wave.open(str(sound_path(name)), "rb") as wav:
            frames = iter(lambda: wav.readframes(self._chunk_frames), b"")
            self._play(wav.getsampwidth(), wav.getnchannels(), wav.getframerate(), frames)

    def play_pcm(self, audio: PcmAudio) -> None:
        """Play raw PCM audio, such as a synthesized reply."""
        step = self._chunk_frames * audio.frame_size
        chunks = (audio.data[i : i + step] for i in range(0, len(audio.data), step))
        self._play(audio.sample_width, audio.channels, audio.sample_rate, chunks)

    def play(self, event: ApplicationEvent) -> ApplicationEvent:
        """Pipeline handler for ``PLAY`` events; ``event.request`` is a :class:`PcmAudio`."""
        try:
            self.play_pcm(event.request)
        except OSError as exc:
            log.exception("Audio playback failed")
            return event.fail(f"Audio playback failed: {exc}")
        return event.succeed()

    def _play(self, sample_width: int, channels: int, rate: int, frames: Iterable[bytes]) -> None:
        stream = self._pyaudio.open(
            format=self._pyaudio.get_format_from_width(sample_width),
            channels=channels,
            rate=rate,
            output=True,
        )
        try:
            for chunk in frames:
                stream.write(chunk)
        finally:
            stream.stop_stream()
            stream.close()

    def close(self) -> None:
        self._pyaudio.terminate()
