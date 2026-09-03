"""Text-to-speech with the ElevenLabs REST API.

Audio is requested as raw PCM so it can be written straight to the sound card
by :class:`heddy.audio.player.AudioPlayer`, with no MP3 decoder involved.
"""

from __future__ import annotations

import logging

import requests

from heddy.audio.pcm import PcmAudio
from heddy.config import DEFAULT_TTS_MODEL_ID, DEFAULT_TTS_OUTPUT_FORMAT, DEFAULT_TTS_VOICE_ID
from heddy.exceptions import ConfigError
from heddy.text_to_speech.manager import TTSResult

log = logging.getLogger(__name__)

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def pcm_sample_rate(output_format: str) -> int:
    """Return the sample rate encoded in an ElevenLabs ``pcm_<rate>`` output format."""
    prefix, _, rate = output_format.partition("_")
    if prefix != "pcm" or not rate.isdigit():
        raise ConfigError(
            "ELEVENLABS_OUTPUT_FORMAT must be a pcm_<rate> format such as pcm_24000 so the "
            f"audio can be played directly; got {output_format!r}."
        )
    return int(rate)


class ElevenLabsSynthesizer:
    """Synthesizes speech for one voice and model."""

    def __init__(
        self,
        api_key: str,
        *,
        voice_id: str = DEFAULT_TTS_VOICE_ID,
        model_id: str = DEFAULT_TTS_MODEL_ID,
        output_format: str = DEFAULT_TTS_OUTPUT_FORMAT,
        timeout: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format
        self.sample_rate = pcm_sample_rate(output_format)
        self._timeout = timeout
        self._session = session or requests.Session()

    def synthesize(self, text: str) -> TTSResult:
        payload = {
            "model_id": self.model_id,
            "text": text,
            "voice_settings": {
                "stability": 1.0,
                "similarity_boost": 1.0,
                "style": 1.0,
                "use_speaker_boost": True,
            },
        }
        try:
            response = self._session.post(
                API_URL.format(voice_id=self.voice_id),
                params={"output_format": self.output_format},
                json=payload,
                headers={"xi-api-key": self._api_key},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            log.exception("ElevenLabs request failed")
            return TTSResult.failed(f"ElevenLabs request failed: {exc}")

        if response.status_code != 200:
            return TTSResult.failed(
                f"ElevenLabs returned HTTP {response.status_code}: {response.text[:200]}"
            )
        if not response.content:
            return TTSResult.failed("ElevenLabs returned no audio.")
        return TTSResult.ok(PcmAudio(response.content, sample_rate=self.sample_rate))
