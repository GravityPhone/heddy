import wave

import pytest

from heddy import resources
from heddy.keyword_detector import KeywordDetector


@pytest.mark.parametrize("name", resources.ALL_SOUNDS)
def test_every_sound_effect_is_a_readable_wav(name):
    with wave.open(str(resources.sound_path(name))) as wav:
        assert wav.getnframes() > 0
        assert wav.getsampwidth() == 2


def test_unknown_sound_is_rejected():
    with pytest.raises(FileNotFoundError):
        resources.sound_path("missing.wav")


def test_keyword_file_lists_the_command_words():
    assert resources.KEYWORDS_FILE.is_file()
    assert KeywordDetector().keywords() == ["computer", "reply", "snapshot"]
