"""Microphone capture to a WAV file on a background thread."""

from __future__ import annotations

import logging
import tempfile
import threading
import wave
from pathlib import Path

import pyaudio

from heddy.audio.quiet import suppress_stderr
from heddy.exceptions import RecordingError

log = logging.getLogger(__name__)


class AudioRecorder:
    """Records 16 kHz mono audio between :meth:`start` and :meth:`stop`.

    The recording is written to ``output_path`` (by default a file in the system
    temporary directory) so the transcriber can upload it.
    """

    def __init__(
        self,
        output_path: Path | str | None = None,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_frames: int = 1024,
        input_device_index: int | None = None,
    ) -> None:
        default_path = Path(tempfile.gettempdir()) / "heddy_recording.wav"
        self.output_path = Path(output_path) if output_path else default_path
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunk_frames = chunk_frames
        self._input_device_index = input_device_index
        self._recording = False
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Begin capturing audio. Calling this while recording is a no-op."""
        if self._recording:
            return
        self._recording = True
        self._error = None
        self._thread = threading.Thread(target=self._record, name="heddy-recorder", daemon=True)
        self._thread.start()
        log.info("Recording started")

    def stop(self) -> Path:
        """Stop capturing and return the path of the finished WAV file."""
        if not self._recording:
            return self.output_path
        self._recording = False
        if self._thread is not None:
            self._thread.join()
        log.info("Recording stopped")
        if self._error is not None:
            raise RecordingError(f"Could not record from the microphone: {self._error}")
        return self.output_path

    def _record(self) -> None:
        frames: list[bytes] = []
        try:
            with suppress_stderr():
                audio = pyaudio.PyAudio()
            try:
                stream = audio.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self._chunk_frames,
                    input_device_index=self._input_device_index,
                )
                try:
                    while self._recording:
                        frames.append(stream.read(self._chunk_frames, exception_on_overflow=False))
                finally:
                    stream.stop_stream()
                    stream.close()
                sample_width = audio.get_sample_size(pyaudio.paInt16)
            finally:
                audio.terminate()

            with wave.open(str(self.output_path), "wb") as wav:
                wav.setnchannels(self.channels)
                wav.setsampwidth(sample_width)
                wav.setframerate(self.sample_rate)
                wav.writeframes(b"".join(frames))
        except Exception as exc:  # surfaced to the caller by stop()
            log.exception("Recording failed")
            self._error = exc
            self._recording = False
