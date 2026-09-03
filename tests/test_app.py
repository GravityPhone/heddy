import pytest

from heddy import __version__
from heddy.app import build_tools, main
from heddy.config import Settings

REQUIRED = {"OPENAI_API_KEY": "a", "ASSEMBLYAI_API_KEY": "b", "ELEVENLABS_API_KEY": "c"}


@pytest.fixture
def clean_env(monkeypatch):
    for name in (*REQUIRED, "ZAPIER_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)


def test_main_explains_missing_configuration(clean_env, tmp_path, capsys):
    exit_code = main(["--env-file", str(tmp_path / "absent.env")])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "OPENAI_API_KEY" in err and "ASSEMBLYAI_API_KEY" in err


def test_main_loads_the_dotenv_file_it_is_given(clean_env, tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text("OPENAI_API_KEY=x\nASSEMBLYAI_API_KEY=y\nELEVENLABS_API_KEY=z\n")
    built = {}

    class StoppedController:
        def run(self):
            built["ran"] = True

    monkeypatch.setattr("heddy.app.build_controller", lambda settings: StoppedController())
    assert main(["--env-file", str(env_file)]) == 0
    assert built == {"ran": True}


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_tools_depend_on_configuration():
    assert build_tools(Settings.from_env(REQUIRED)) == []
    with_zapier = Settings.from_env({**REQUIRED, "ZAPIER_WEBHOOK_URL": "https://hooks.example/1"})
    assert [tool.name for tool in build_tools(with_zapier)] == ["send_text_message"]
