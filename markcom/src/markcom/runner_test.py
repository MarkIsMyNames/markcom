import json
import logging

import pytest
from pydantic import SecretStr

from markcom.config import BaseAppConfig
from markcom.runner import ExitCode, run
from markcom.secrets import BaseSecrets


class ExampleConfig(BaseAppConfig):
    greeting: str


class ExampleSecrets(BaseSecrets):
    api_token: SecretStr


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_TOKEN", "t")
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"log_level": "DEBUG", "greeting": "Dia duit"}), encoding="utf-8")
    return path


def test_passes_loaded_config_and_secrets_to_main_with_logging_configured(config_path):
    received = []

    def main(config, secrets):
        received.append((config.greeting, secrets.api_token.get_secret_value()))
        assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

    run(main, config_path=config_path, config_model=ExampleConfig, secrets_model=ExampleSecrets)
    assert received == [("Dia duit", "t")]


def test_exits_with_config_error_before_main_runs(config_path, monkeypatch, capsys):
    monkeypatch.delenv("API_TOKEN")
    called = []
    with pytest.raises(SystemExit) as exit_info:
        run(
            lambda *_: called.append(True),
            config_path=config_path,
            config_model=ExampleConfig,
            secrets_model=ExampleSecrets,
        )
    assert exit_info.value.code == ExitCode.CONFIG_ERROR
    assert "api_token" in capsys.readouterr().err
    assert called == []


def test_lets_errors_from_main_propagate(config_path):
    def main(_config, _secrets):
        raise RuntimeError

    with pytest.raises(RuntimeError):
        run(main, config_path=config_path, config_model=ExampleConfig, secrets_model=ExampleSecrets)


def test_reads_variables_from_a_dotenv_file(config_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN")
    (config_path.parent / ".env").write_text("API_TOKEN=from-file\n", encoding="utf-8")
    received = []
    run(
        lambda _config, secrets: received.append(secrets.api_token.get_secret_value()),
        config_path=config_path,
        config_model=ExampleConfig,
        secrets_model=ExampleSecrets,
    )
    assert received == ["from-file"]


def test_returns_what_main_returns(config_path):
    result = run(
        lambda config, _secrets: config.greeting,
        config_path=config_path,
        config_model=ExampleConfig,
        secrets_model=ExampleSecrets,
    )
    assert result == "Dia duit"
