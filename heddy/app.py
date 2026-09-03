"""Composition root and command-line entry point.

This is the only module that knows about every concrete provider. It reads the
settings, builds the pipeline components, injects them into the controller and
runs the loop. Run it with ``python -m heddy`` or the ``heddy`` console script.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

import openai
from dotenv import load_dotenv

from heddy import __version__
from heddy.assistant.conversation import Conversation
from heddy.assistant.manager import AssistantManager
from heddy.assistant.tools import Tool, ToolRegistry, ZapierWebhook, send_text_message_tool
from heddy.audio.player import AudioPlayer
from heddy.audio.recorder import AudioRecorder
from heddy.config import Settings
from heddy.controller import MainController
from heddy.exceptions import ConfigError
from heddy.keyword_detector import KeywordDetector
from heddy.resources import CONVERSATION_RESET_SOUND
from heddy.speech_to_text.assemblyai_transcriber import AssemblyAITranscriber
from heddy.speech_to_text.manager import STTManager
from heddy.text_to_speech.eleven_labs import ElevenLabsSynthesizer
from heddy.text_to_speech.manager import TTSManager
from heddy.vision import Camera

log = logging.getLogger(__name__)


def build_tools(settings: Settings) -> list[Tool]:
    """Tools are enabled only when their integration is configured."""
    tools: list[Tool] = []
    if settings.zapier_webhook_url:
        tools.append(send_text_message_tool(ZapierWebhook(settings.zapier_webhook_url)))
    else:
        log.info("ZAPIER_WEBHOOK_URL is not set; the send_text_message tool is disabled")
    return tools


def build_controller(settings: Settings) -> MainController:
    """Wire every component together."""
    player = AudioPlayer()
    conversation = Conversation(
        timeout=settings.conversation_timeout,
        on_reset=lambda: player.play_sound(CONVERSATION_RESET_SOUND),
    )
    assistant = AssistantManager(
        openai.OpenAI(api_key=settings.openai_api_key),
        conversation=conversation,
        tools=ToolRegistry(build_tools(settings)),
        model=settings.model,
        instructions=settings.instructions,
        max_output_tokens=settings.max_output_tokens,
    )
    synthesizer = ElevenLabsSynthesizer(
        settings.elevenlabs_api_key,
        voice_id=settings.tts_voice_id,
        model_id=settings.tts_model_id,
        output_format=settings.tts_output_format,
    )
    return MainController(
        assistant=assistant,
        transcriber=STTManager(AssemblyAITranscriber(settings.assemblyai_api_key)),
        synthesizer=TTSManager(synthesizer),
        audio_player=player,
        recorder=AudioRecorder(),
        camera=Camera(settings.camera_device),
        keyword_detector=KeywordDetector(),
    )


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "httpcore", "urllib3", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heddy", description="Run the Heddy voice assistant.")
    parser.add_argument("--env-file", default=".env", help="dotenv file to load (default: .env)")
    parser.add_argument("--version", action="version", version=f"heddy {__version__}")
    args = parser.parse_args(argv)

    load_dotenv(args.env_file)
    configure_logging()
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"heddy: {exc}", file=sys.stderr)
        return 2
    logging.getLogger().setLevel(settings.log_level)

    log.info("Starting Heddy %s (model: %s)", __version__, settings.model)
    build_controller(settings).run()
    return 0
