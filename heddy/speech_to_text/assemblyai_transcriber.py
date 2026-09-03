"""Transcription with AssemblyAI's batch API."""

from __future__ import annotations

import logging
from pathlib import Path

import assemblyai as aai

from heddy.speech_to_text.manager import STTResult

log = logging.getLogger(__name__)


class AssemblyAITranscriber:
    """Uploads a recording to AssemblyAI and waits for the transcript."""

    def __init__(self, api_key: str) -> None:
        aai.settings.api_key = api_key

    def transcribe_file(self, path: Path) -> STTResult:
        log.info("Transcribing %s", path)
        try:
            transcript = aai.Transcriber().transcribe(str(path))
        except Exception as exc:  # network errors, bad key, unreadable file
            log.exception("AssemblyAI request failed")
            return STTResult.failed(f"AssemblyAI request failed: {exc}")

        if transcript.status == aai.TranscriptStatus.error:
            return STTResult.failed(transcript.error or "AssemblyAI reported an error.")

        text = (transcript.text or "").strip()
        if not text:
            return STTResult.failed("No speech was detected in the recording.")
        return STTResult.ok(text)
