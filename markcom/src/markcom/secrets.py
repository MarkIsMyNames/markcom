from pathlib import Path
from typing import ClassVar, Self, override

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from markcom.config import ConfigError

ENV_FILE: str = ".env"


class BaseSecrets(BaseSettings):
    """Base for secrets: each field is read from its upper-case variable (api_token: API_TOKEN),
    from the environment first, then from the .env in load's folder. Unknown .env keys are
    rejected; immutable. Validation errors never echo a value, so a secret can't reach a log or
    the terminal."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=ENV_FILE, extra="forbid", frozen=True, hide_input_in_errors=True
    )

    @classmethod
    def load(cls, env_dir: Path) -> Self:
        """Read from the environment and `env_dir`'s .env, not the working directory's: an app
        started from the desktop menu runs in the home folder."""
        return cls(_env_file=env_dir / ENV_FILE)


class NoSecrets(BaseSecrets):
    """For apps that read no environment variables. It ignores any .env, so the app can run
    from a folder whose .env belongs to something else."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_file=None)

    @classmethod
    @override
    def load(cls, env_dir: Path) -> Self:
        return cls()


def load_secrets[TSecrets: BaseSecrets](model: type[TSecrets], env_dir: Path) -> TSecrets:
    try:
        return model.load(env_dir)
    except ValidationError as error:
        message: str = f"missing or invalid environment variables (see .env.example): {error}"
        raise ConfigError(message) from error
