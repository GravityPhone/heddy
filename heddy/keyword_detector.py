"""Always-on keyword spotting with PocketSphinx.

A background thread streams microphone audio through PocketSphinx's endpointer
(which finds utterances) and a decoder in keyword-search mode (which finds the
command words inside them). Detected words are queued for the controller,
which blocks in :meth:`KeywordDetector.listen` between pipeline stages.

The keywords and their detection thresholds live in ``resources/keywords.kws``.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path

import pyaudio
from pocketsphinx import Decoder, Endpointer

from heddy.audio.quiet import suppress_stderr
from heddy.events import ApplicationEvent
from heddy.resources import KEYWORDS_FILE

log = logging.getLogger(__name__)

_STOPPED = None  # queue sentinel: the detection thread has died


class KeywordDetector:
    def __init__(
        self,
        keywords_file: Path | str = KEYWORDS_FILE,
        *,
        sample_rate: int = 16000,
        input_device_index: int | None = None,
    ) -> None:
        self.keywords_file = Path(keywords_file)
        self.sample_rate = sample_rate
        self.frame_bytes = Endpointer(sample_rate=sample_rate).frame_bytes
        self._input_device_index = input_device_index
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None
        self._suspended = False

    def keywords(self) -> list[str]:
        """The phrases listed in the keyword file."""
        phrases = []
        for line in self.keywords_file.read_text().splitlines():
            phrase = line.split("/")[0].strip()
            if phrase:
                phrases.append(phrase)
        return phrases

    # -- pipeline interface -------------------------------------------------------

    def listen(self, event: ApplicationEvent) -> ApplicationEvent:
        """Pipeline handler for ``LISTEN``: block until a keyword is heard."""
        if self._thread is None:
            self._start_thread()
        self._suspended = False
        word = self._queue.get()
        if word is _STOPPED:
            raise RuntimeError(f"Keyword detection stopped: {self._failure}")
        return event.succeed(word)

    def clear(self) -> None:
        """Drop queued words and ignore new ones until the next :meth:`listen`.

        Called when recording stops, so that command words inside the assistant's
        spoken reply cannot trigger a new interaction.
        """
        self._suspended = True
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    # -- detection ----------------------------------------------------------------

    def detect(self, frames: Iterable[bytes]) -> Iterator[list[str]]:
        """Yield the keywords found in each utterance of a 16-bit mono PCM stream.

        ``frames`` must be chunks of exactly :attr:`frame_bytes` bytes; a shorter
        chunk marks the end of the stream. This is the pure part of the detector
        and can be driven from a file as well as a microphone.
        """
        endpointer = Endpointer(sample_rate=self.sample_rate)
        decoder = Decoder(kws=str(self.keywords_file), lm=None, samprate=self.sample_rate)
        in_utterance = False

        for frame in frames:
            final = len(frame) != endpointer.frame_bytes
            speech = endpointer.end_stream(frame) if final else endpointer.process(frame)
            if speech is not None:
                if not in_utterance:
                    decoder.start_utt()
                    in_utterance = True
                decoder.process_raw(speech)
                if not endpointer.in_speech:
                    decoder.end_utt()
                    in_utterance = False
                    words = self._words(decoder)
                    if words:
                        yield words
            if final:
                break

        if in_utterance:
            decoder.end_utt()
            words = self._words(decoder)
            if words:
                yield words

    @staticmethod
    def _words(decoder: Decoder) -> list[str]:
        if decoder.hyp() is None:
            return []
        return [segment.word.lower().strip() for segment in decoder.seg()]

    # -- microphone thread --------------------------------------------------------

    def _start_thread(self) -> None:
        self._thread = threading.Thread(target=self._run, name="heddy-keywords", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        log.info("Listening for keywords: %s", ", ".join(self.keywords()))
        try:
            for words in self.detect(self._microphone_frames()):
                log.debug("Heard %s", words)
                if self._suspended:
                    continue
                for word in words:
                    self._queue.put(word)
        except BaseException as exc:  # let listen() report the failure on the main thread
            log.exception("Keyword detection stopped")
            self._failure = exc
            self._queue.put(_STOPPED)

    def _microphone_frames(self) -> Iterator[bytes]:
        frames_per_buffer = self.frame_bytes // 2  # 16-bit samples
        with suppress_stderr():
            audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=frames_per_buffer,
            input_device_index=self._input_device_index,
        )
        try:
            while True:
                yield stream.read(frames_per_buffer, exception_on_overflow=False)
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()
