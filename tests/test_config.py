import pytest

from heddy import config
from heddy.config import Settings
from heddy.exceptions import ConfigError

REQUIRED = {
    "OPENAI_API_KEY": "sk-test",
    "ASSEMBLYAI_API_KEY": "aai-test",
    "ELEVENLABS_API_KEY": "el-test",
}


def test_missing_keys_are_all_reported_at_once():
    with pytest.raises(ConfigError) as info:
        Settings.from_env({"OPENAI_API_KEY": "sk-test", "ELEVENLABS_API_KEY": "  "})
    message = str(info.value)
    assert "ASSEMBLYAI_API_KEY" in message
    assert "ELEVENLABS_API_KEY" in message
    assert "OPENAI_API_KEY" not in message
    assert ".env.example" in message


def test_defaults_apply_when_optional_variables_are_absent():
    settings = Settings.from_env(REQUIRED)
    assert settings.openai_api_key == "sk-test"
    assert settings.model == config.DEFAULT_MODEL
    assert settings.instructions == config.DEFAULT_INSTRUCTIONS
    assert settings.max_output_tokens == config.DEFAULT_MAX_OUTPUT_TOKENS
    assert settings.conversation_timeout == config.DEFAULT_CONVERSATION_TIMEOUT
    assert settings.zapier_webhook_url is None
    assert settings.camera_device == config.DEFAULT_CAMERA_DEVICE
    assert settings.tts_voice_id == config.DEFAULT_TTS_VOICE_ID
    assert settings.tts_output_format == config.DEFAULT_TTS_OUTPUT_FORMAT
    assert settings.log_level == "INFO"


def test_overrides_are_read_and_trimmed():
    settings = Settings.from_env(
        {
            **REQUIRED,
            "OPENAI_API_KEY": "  sk-spaced  ",
            "HEDDY_MODEL": "gpt-4.1",
            "HEDDY_INSTRUCTIONS": "Be terse.",
            "HEDDY_MAX_OUTPUT_TOKENS": "120",
            "HEDDY_CONVERSATION_TIMEOUT": "45.5",
            "ZAPIER_WEBHOOK_URL": "https://hooks.zapier.com/hooks/catch/1/abc/",
            "HEDDY_CAMERA_DEVICE": "/dev/video2",
            "ELEVENLABS_VOICE_ID": "voice",
            "ELEVENLABS_MODEL_ID": "eleven_flash_v2_5",
            "ELEVENLABS_OUTPUT_FORMAT": "pcm_16000",
            "HEDDY_LOG_LEVEL": "debug",
        }
    )
    assert settings.openai_api_key == "sk-spaced"
    assert settings.model == "gpt-4.1"
    assert settings.instructions == "Be terse."
    assert settings.max_output_tokens == 120
    assert settings.conversation_timeout == 45.5
    assert settings.zapier_webhook_url == "https://hooks.zapier.com/hooks/catch/1/abc/"
    assert settings.camera_device == "/dev/video2"
    assert settings.tts_voice_id == "voice"
    assert settings.tts_model_id == "eleven_flash_v2_5"
    assert settings.tts_output_format == "pcm_16000"
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_invalid_numbers_are_rejected(value):
    with pytest.raises(ConfigError) as info:
        Settings.from_env({**REQUIRED, "HEDDY_CONVERSATION_TIMEOUT": value})
    assert "HEDDY_CONVERSATION_TIMEOUT" in str(info.value)


def test_process_environment_is_used_by_default(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("HEDDY_MODEL", "from-environ")
    assert Settings.from_env().model == "from-environ"
