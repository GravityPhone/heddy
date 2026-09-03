"""Player and recorder against a fake PyAudio, plus the stderr silencer."""

import os
import time
import wave

import pytest

import heddy.audio.player as player_module
import heddy.audio.recorder as recorder_module
from heddy.audio.pcm import PcmAudio
from heddy.audio.player import AudioPlayer
from heddy.audio.quiet import suppress_stderr
from heddy.audio.recorder import AudioRecorder
from heddy.events import ApplicationEvent, ApplicationEventType
from heddy.exceptions import RecordingError
from heddy.resources import LISTENING_SOUND


class FakeStream:
    def __init__(self, fail_on_write=False):
        self.written = []
        self.reads = 0
        self.closed = False
        self.fail_on_write = fail_on_write

    def write(self, data):
        if self.fail_on_write:
            raise OSError("device unavailable")
        self.written.append(data)

    def read(self, frames, exception_on_overflow=True):
        self.reads += 1
        time.sleep(0.001)
        return b"\x01\x00" * frames

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class FakePyAudioModule:
    paInt16 = 8  # noqa: N815 - mirrors the real module's attribute name

    def __init__(self, stream=None, open_error=None):
        self.stream = stream or FakeStream()
        self.open_error = open_error
        self.opens = []
        self.terminated = False

    # Behave like both the module (`pyaudio.PyAudio()`) and the instance it returns.
    def PyAudio(self):  # noqa: N802
        return self

    def open(self, **kwargs):
        if self.open_error:
            raise self.open_error
        self.opens.append(kwargs)
        return self.stream

    def get_format_from_width(self, width):
        return width

    def get_sample_size(self, fmt):
        return 2

    def terminate(self):
        self.terminated = True


@pytest.fixture
def fake_pyaudio(monkeypatch):
    fake = FakePyAudioModule()
    monkeypatch.setattr(player_module, "pyaudio", fake)
    monkeypatch.setattr(recorder_module, "pyaudio", fake)
    return fake


def test_player_streams_bundled_wav_files(fake_pyaudio):
    player = AudioPlayer(chunk_frames=256)
    player.play_sound(LISTENING_SOUND)
    assert fake_pyaudio.opens[0]["output"] is True
    assert fake_pyaudio.opens[0]["rate"] == 16000
    assert b"".join(fake_pyaudio.stream.written)
    assert fake_pyaudio.stream.closed
    player.close()
    assert fake_pyaudio.terminated


def test_player_unknown_sound_is_a_clear_error(fake_pyaudio):
    with pytest.raises(FileNotFoundError, match="Unknown sound"):
        AudioPlayer().play_sound("nope.wav")


def test_player_plays_pcm_in_chunks(fake_pyaudio):
    audio = PcmAudio(bytes(range(256)) * 5, sample_rate=24000)
    AudioPlayer(chunk_frames=100).play_pcm(audio)
    assert fake_pyaudio.opens[0]["rate"] == 24000
    assert fake_pyaudio.opens[0]["channels"] == 1
    assert [len(chunk) for chunk in fake_pyaudio.stream.written] == [200] * 6 + [80]
    assert b"".join(fake_pyaudio.stream.written) == audio.data


def test_player_reports_device_errors_through_the_event(fake_pyaudio):
    fake_pyaudio.stream.fail_on_write = True
    event = AudioPlayer().play(
        ApplicationEvent(ApplicationEventType.PLAY, request=PcmAudio(b"\x00\x00", 8000))
    )
    assert not event.ok and "device unavailable" in event.error


def test_recorder_writes_a_wav_file(fake_pyaudio, tmp_path):
    recorder = AudioRecorder(tmp_path / "rec.wav", chunk_frames=64)
    assert not recorder.is_recording
    recorder.start()
    assert recorder.is_recording
    time.sleep(0.02)
    path = recorder.stop()

    assert path == tmp_path / "rec.wav"
    with wave.open(str(path)) as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 16000
        assert wav.getsampwidth() == 2
        assert wav.getnframes() > 0
    assert fake_pyaudio.opens[0]["input"] is True
    assert fake_pyaudio.stream.closed and fake_pyaudio.terminated


def test_recorder_start_is_idempotent_and_stop_without_start_is_harmless(fake_pyaudio, tmp_path):
    recorder = AudioRecorder(tmp_path / "rec.wav")
    assert recorder.stop() == tmp_path / "rec.wav"
    recorder.start()
    recorder.start()
    recorder.stop()
    assert len(fake_pyaudio.opens) == 1


def test_recorder_surfaces_device_failures(fake_pyaudio, tmp_path):
    fake_pyaudio.open_error = OSError("no input device")
    recorder = AudioRecorder(tmp_path / "rec.wav")
    recorder.start()
    with pytest.raises(RecordingError, match="no input device"):
        recorder.stop()
    assert not recorder.is_recording


def test_suppress_stderr_silences_the_file_descriptor(capfd):
    with suppress_stderr():
        os.write(2, b"alsa noise\n")
    os.write(2, b"visible\n")
    assert capfd.readouterr().err == "visible\n"
