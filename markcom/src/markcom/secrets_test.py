import pytest
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from markcom.config import ConfigError
from markcom.secrets import BaseSecrets, NoSecrets, load_secrets


class ExampleSecrets(BaseSecrets):
    api_token: SecretStr
    port: int


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Clears the environment, then sets the given variables and writes .env into the folder it
    returns."""
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    def apply(environ, dotenv):
        for name, value in environ.items():
            monkeypatch.setenv(name, value)
        if dotenv is not None:
            (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
        return tmp_path

    return apply


@pytest.mark.parametrize(
    ("environ", "dotenv", "token"),
    [
        ({"API_TOKEN": "from-env", "PORT": "8080"}, None, "from-env"),
        ({}, "API_TOKEN=from-file\nPORT=8080\n", "from-file"),
        ({"API_TOKEN": "from-env"}, "API_TOKEN=from-file\nPORT=8080\n", "from-env"),
    ],
)
def test_reads_secrets(setup, environ, dotenv, token):
    secrets = load_secrets(ExampleSecrets, setup(environ, dotenv))
    assert secrets.api_token.get_secret_value() == token
    assert secrets.port == 8080


@pytest.mark.parametrize(
    ("model", "environ", "dotenv", "match"),
    [
        (ExampleSecrets, {}, None, r"(?s)api_token.*port"),
        (ExampleSecrets, {"API_TOKEN": "t", "PORT": "eighty"}, None, "port"),
        (ExampleSecrets, {"API_TOKEN": "t", "PORT": "1"}, "UNKNOWN=x\n", "unknown"),
    ],
)
def test_rejects_bad_secrets(setup, model, environ, dotenv, match):
    folder = setup(environ, dotenv)
    with pytest.raises(ConfigError, match=match):
        load_secrets(model, folder)


@pytest.mark.parametrize("dotenv", [None, "SOMEONE_ELSES=x\n"])
def test_no_secrets_needs_no_variables_and_ignores_dotenv(setup, dotenv):
    assert load_secrets(NoSecrets, setup({}, dotenv)) == NoSecrets()


class RootDotenvSecrets(ExampleSecrets):
    """A tool in a subfolder sharing the repository root's .env."""

    model_config = SettingsConfigDict(env_file="../.env")


def test_a_subclass_env_file_is_taken_relative_to_the_folder_given(setup):
    root = setup({}, "API_TOKEN=from-root\nPORT=8080\n")
    tool = root / "tool"
    tool.mkdir()
    assert load_secrets(RootDotenvSecrets, tool).api_token.get_secret_value() == "from-root"
