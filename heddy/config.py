"""Runtime configuration.

Everything Heddy needs from the outside world (API keys, model names, device
paths) comes from environment variables, so nothing sensitive lives in the
repository. ``python-dotenv`` loads a local ``.env`` file at start-up; see
``.env.example`` for the full list of variables.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from heddy.exceptions import ConfigError

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_OUTPUT_TOKENS = 300
DEFAULT_CONVERSATION_TIMEOUT = 90.0
DEFAULT_CAMERA_DEVICE = "/dev/video0"
DEFAULT_TTS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel", one of ElevenLabs' stock voices
DEFAULT_TTS_MODEL_ID = "eleven_turbo_v2"
DEFAULT_TTS_OUTPUT_FORMAT = "pcm_24000"
DEFAULT_LOG_LEVEL = "INFO"

DEFAULT_INSTRUCTIONS = (
    "You are Heddy, a hands-free voice assistant. Your replies are read aloud by a "
    "text-to-speech engine, so answer in plain conversational sentences: no markdown, "
    "no lists, no code. Keep replies to one or two sentences unless the user asks for "
    "detail. If an image is attached, use what you can see in it. When you send a text "
    "message on the user's behalf, confirm briefly what you sent."
)

REQUIRED_VARIABLES = ("OPENAI_API_KEY", "ASSEMBLYAI_API_KEY", "ELEVENLABS_API_KEY")

_Number = TypeVar("_Number", int, float)


@dataclass(frozen=True)
class Settings:
    """Validated application settings."""

    openai_api_key: str
    assemblyai_api_key: str
    elevenlabs_api_key: str
    model: str = DEFAULT_MODEL
    instructions: str = DEFAULT_INSTRUCTIONS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    conversation_timeout: float = DEFAULT_CONVERSATION_TIMEOUT
    zapier_webhook_url: str | None = None
    camera_device: str = DEFAULT_CAMERA_DEVICE
    tts_voice_id: str = DEFAULT_TTS_VOICE_ID
    tts_model_id: str = DEFAULT_TTS_MODEL_ID
    tts_output_format: str = DEFAULT_TTS_OUTPUT_FORMAT
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``env`` (default: the process environment).

        Raises :class:`ConfigError` naming every missing required variable, so a
        first-time user sees the whole list at once rather than one at a time.
        """
        source = os.environ if env is None else env
        missing = [name for name in REQUIRED_VARIABLES if not _text(source, name)]
        if missing:
            raise ConfigError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in your keys."
            )
        return cls(
            openai_api_key=_text(source, "OPENAI_API_KEY"),
            assemblyai_api_key=_text(source, "ASSEMBLYAI_API_KEY"),
            elevenlabs_api_key=_text(source, "ELEVENLABS_API_KEY"),
            model=_text(source, "HEDDY_MODEL") or DEFAULT_MODEL,
            instructions=_text(source, "HEDDY_INSTRUCTIONS") or DEFAULT_INSTRUCTIONS,
            max_output_tokens=_positive(
                source, "HEDDY_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, int
            ),
            conversation_timeout=_positive(
                source, "HEDDY_CONVERSATION_TIMEOUT", DEFAULT_CONVERSATION_TIMEOUT, float
            ),
            zapier_webhook_url=_text(source, "ZAPIER_WEBHOOK_URL") or None,
            camera_device=_text(source, "HEDDY_CAMERA_DEVICE") or DEFAULT_CAMERA_DEVICE,
            tts_voice_id=_text(source, "ELEVENLABS_VOICE_ID") or DEFAULT_TTS_VOICE_ID,
            tts_model_id=_text(source, "ELEVENLABS_MODEL_ID") or DEFAULT_TTS_MODEL_ID,
            tts_output_format=_text(source, "ELEVENLABS_OUTPUT_FORMAT")
            or DEFAULT_TTS_OUTPUT_FORMAT,
            log_level=(_text(source, "HEDDY_LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper(),
        )


def _text(source: Mapping[str, str], name: str) -> str:
    return (source.get(name) or "").strip()


def _positive(
    source: Mapping[str, str], name: str, default: _Number, cast: Callable[[str], _Number]
) -> _Number:
    raw = _text(source, name)
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}.") from None
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {raw!r}.")
    return value
