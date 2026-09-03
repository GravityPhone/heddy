"""Speech-to-text and text-to-speech adapters."""

from pathlib import Path

import pytest
import requests

from heddy.audio.pcm import PcmAudio
from heddy.events import ApplicationEvent, ApplicationEventType
from heddy.exceptions import ConfigError
from heddy.speech_to_text.manager import STTManager, STTResult, STTStatus
from heddy.text_to_speech.eleven_labs import ElevenLabsSynthesizer, pcm_sample_rate
from heddy.text_to_speech.manager import TTSManager, TTSResult, TTSStatus


class FakeResponse:
    def __init__(self, status_code=200, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


# -- speech to text -----------------------------------------------------------------


def test_stt_manager_maps_success_to_the_event():
    class Transcriber:
        def transcribe_file(self, path):
            assert isinstance(path, Path)
            return STTResult.ok("hello world")

    event = STTManager(Transcriber()).transcribe(
        ApplicationEvent(ApplicationEventType.TRANSCRIBE, request="rec.wav")
    )
    assert event.ok and event.result == "hello world"


def test_stt_manager_maps_failure_to_the_event():
    class Transcriber:
        def transcribe_file(self, path):
            return STTResult.failed("bad key")

    event = STTManager(Transcriber()).transcribe(
        ApplicationEvent(ApplicationEventType.TRANSCRIBE, request="rec.wav")
    )
    assert not event.ok and event.error == "bad key"


def test_stt_result_constructors():
    assert STTResult.ok("x") == STTResult(STTStatus.SUCCESS, text="x")
    assert STTResult.failed("e") == STTResult(STTStatus.ERROR, error="e")


# -- text to speech -----------------------------------------------------------------


def test_tts_manager_maps_results_to_the_event():
    audio = PcmAudio(b"\x00\x01", 24000)

    class Synth:
        def synthesize(self, text):
            return TTSResult.ok(audio) if text == "hi" else TTSResult.failed("quota")

    manager = TTSManager(Synth())
    ok = manager.synthesize(ApplicationEvent(ApplicationEventType.SYNTHESIZE, request="hi"))
    assert ok.ok and ok.result is audio
    bad = manager.synthesize(ApplicationEvent(ApplicationEventType.SYNTHESIZE, request="bye"))
    assert not bad.ok
    assert bad.error == "quota"


def test_pcm_sample_rate_parsing():
    assert pcm_sample_rate("pcm_24000") == 24000
    assert pcm_sample_rate("pcm_16000") == 16000
    for bad in ("mp3_44100_128", "pcm_", "wav_16000", "pcm"):
        with pytest.raises(ConfigError):
            pcm_sample_rate(bad)


def test_elevenlabs_request_shape_and_success():
    session = FakeSession(FakeResponse(content=b"\x01\x00" * 100))
    synth = ElevenLabsSynthesizer(
        "secret", voice_id="v1", model_id="m1", output_format="pcm_16000", session=session
    )

    result = synth.synthesize("Hello there")

    assert result.status is TTSStatus.SUCCESS
    assert result.audio == PcmAudio(b"\x01\x00" * 100, sample_rate=16000)
    url, kwargs = session.calls[0]
    assert url == "https://api.elevenlabs.io/v1/text-to-speech/v1"
    assert kwargs["params"] == {"output_format": "pcm_16000"}
    assert kwargs["headers"] == {"xi-api-key": "secret"}
    assert kwargs["json"]["model_id"] == "m1"
    assert kwargs["json"]["text"] == "Hello there"
    assert kwargs["timeout"] == 60.0


def test_elevenlabs_http_error_is_reported():
    session = FakeSession(FakeResponse(status_code=401, text='{"detail": "invalid key"}'))
    result = ElevenLabsSynthesizer("bad", session=session).synthesize("hi")
    assert result.status is TTSStatus.ERROR
    assert "401" in result.error and "invalid key" in result.error


def test_elevenlabs_network_error_is_reported():
    session = FakeSession(error=requests.ConnectionError("dns failure"))
    result = ElevenLabsSynthesizer("k", session=session).synthesize("hi")
    assert result.status is TTSStatus.ERROR
    assert "dns failure" in result.error


def test_elevenlabs_empty_body_is_an_error():
    result = ElevenLabsSynthesizer("k", session=FakeSession(FakeResponse())).synthesize("hi")
    assert result.status is TTSStatus.ERROR


def test_pcm_audio_geometry():
    audio = PcmAudio(b"\x00" * 48000, sample_rate=24000)
    assert audio.frame_size == 2
    assert audio.duration == 1.0
    stereo = PcmAudio(b"\x00" * 4, sample_rate=1, channels=2)
    assert stereo.frame_size == 4 and stereo.duration == 1.0
