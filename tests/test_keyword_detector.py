"""Keyword detector mechanics, without a microphone.

Recognition quality itself needs real speech, so these tests cover the parts
around PocketSphinx: framing, the utterance loop on silence, the word queue,
and how a dead detection thread is reported.
"""

import queue
import shutil
import subprocess
import wave

import pytest

from heddy.events import ApplicationEvent, ApplicationEventType
from heddy.keyword_detector import KeywordDetector


def silence(detector: KeywordDetector, seconds: float) -> list[bytes]:
    total = int(detector.sample_rate * 2 * seconds)
    data = b"\x00" * total
    step = detector.frame_bytes
    return [data[i : i + step] for i in range(0, total, step)]


def test_frame_size_matches_the_endpointer():
    detector = KeywordDetector()
    assert detector.frame_bytes > 0
    assert detector.frame_bytes % 2 == 0


def test_silence_yields_no_keywords():
    detector = KeywordDetector()
    assert list(detector.detect(silence(detector, 1.5))) == []


def test_a_short_final_frame_ends_the_stream_cleanly():
    detector = KeywordDetector()
    frames = silence(detector, 0.5) + [b"\x00" * 10, b"\x00" * detector.frame_bytes]
    assert list(detector.detect(frames)) == []


def test_keywords_are_parsed_from_the_file(tmp_path):
    kws = tmp_path / "words.kws"
    kws.write_text("hey heddy /1e-20/\n\nstop /1e-5/\n")
    assert KeywordDetector(kws).keywords() == ["hey heddy", "stop"]


@pytest.fixture
def detector_without_microphone(monkeypatch):
    detector = KeywordDetector()
    monkeypatch.setattr(detector, "_start_thread", lambda: setattr(detector, "_thread", object()))
    return detector


def test_listen_returns_queued_words_in_order(detector_without_microphone):
    detector = detector_without_microphone
    detector._queue.put("computer")
    detector._queue.put("reply")
    first = detector.listen(ApplicationEvent(ApplicationEventType.LISTEN))
    second = detector.listen(ApplicationEvent(ApplicationEventType.LISTEN))
    assert first.ok and first.result == "computer"
    assert second.ok and second.result == "reply"


def test_clear_drops_pending_words_and_mutes_until_next_listen(detector_without_microphone):
    detector = detector_without_microphone
    detector._queue.put("computer")
    detector.clear()
    assert detector._suspended
    with pytest.raises(queue.Empty):
        detector._queue.get_nowait()
    detector._queue.put("reply")
    detector.listen(ApplicationEvent(ApplicationEventType.LISTEN))
    assert not detector._suspended


def test_a_dead_detection_thread_is_reported(detector_without_microphone, monkeypatch):
    detector = detector_without_microphone
    monkeypatch.setattr(detector, "_microphone_frames", lambda: iter([b"\x00" * 10]))
    monkeypatch.setattr(detector, "detect", lambda frames: (_ for _ in ()).throw(OSError("no mic")))
    detector._run()
    with pytest.raises(RuntimeError, match="no mic"):
        detector.listen(ApplicationEvent(ApplicationEventType.LISTEN))


def test_run_queues_detected_words_unless_muted(detector_without_microphone, monkeypatch):
    detector = detector_without_microphone
    monkeypatch.setattr(detector, "_microphone_frames", lambda: iter([]))
    heard = [["computer"], ["snapshot", "reply"]]
    monkeypatch.setattr(detector, "detect", lambda frames: iter(heard))
    detector._run()
    assert [detector._queue.get_nowait() for _ in range(3)] == ["computer", "snapshot", "reply"]

    detector.clear()
    detector._run()
    with pytest.raises(queue.Empty):
        detector._queue.get_nowait()


# -- recognition on synthesized speech ----------------------------------------------
#
# ``flite`` (CMU's small speech synthesizer) produces 16 kHz speech that PocketSphinx
# recognises reliably, so the full endpointer + keyword-search loop can be exercised
# with the project's real keyword file and thresholds.

needs_flite = pytest.mark.skipif(shutil.which("flite") is None, reason="flite is not installed")


def synthesize(text: str, path) -> bytes:
    subprocess.run(
        ["flite", "-voice", "kal16", "-t", text, "-o", str(path)], check=True, capture_output=True
    )
    with wave.open(str(path)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        return wav.readframes(wav.getnframes())


@needs_flite
@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("computer", ["computer"]),
        ("snapshot", ["snapshot"]),
        ("reply", ["reply"]),
        ("computer, snapshot. what is this? reply", ["computer", "snapshot", "reply"]),
        ("hello there how are you today", []),
    ],
)
def test_keywords_are_spotted_in_synthesized_speech(tmp_path, spoken, expected):
    detector = KeywordDetector()
    quiet = b"\x00\x00" * detector.sample_rate  # a second of silence on each side
    audio = quiet + synthesize(spoken, tmp_path / "speech.wav") + quiet
    frames = [
        audio[i : i + detector.frame_bytes] for i in range(0, len(audio), detector.frame_bytes)
    ]

    heard = [word for utterance in detector.detect(frames) for word in utterance]

    assert heard == expected
