"""Bundled resources: the PocketSphinx keyword list and the sound effects."""

from pathlib import Path

RESOURCE_DIR = Path(__file__).resolve().parent
SOUNDS_DIR = RESOURCE_DIR / "sounds"
KEYWORDS_FILE = RESOURCE_DIR / "keywords.kws"

# Sound effects, by the moment in the interaction they mark.
LISTENING_SOUND = "listening.wav"
START_RECORDING_SOUND = "start_recording.wav"
SNAPSHOT_SOUND = "snapshot.wav"
RESPOND_SOUND = "respond.wav"
CONVERSATION_RESET_SOUND = "conversation_reset.wav"

ALL_SOUNDS = (
    LISTENING_SOUND,
    START_RECORDING_SOUND,
    SNAPSHOT_SOUND,
    RESPOND_SOUND,
    CONVERSATION_RESET_SOUND,
)


def get_resource_dir() -> Path:
    return RESOURCE_DIR


def sound_path(name: str) -> Path:
    """Return the absolute path of a bundled sound effect."""
    path = SOUNDS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Unknown sound effect {name!r} (looked in {SOUNDS_DIR})")
    return path
