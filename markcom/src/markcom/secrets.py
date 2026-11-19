from pathlib import Path
from typing import ClassVar, Self

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotenvType

from markcom.config import ConfigError

ENV_FILE: str = ".env"


class BaseSecrets(BaseSettings):
    """Base for secrets: each field is read from its upper-case variable (api_token: API_TOKEN),
    from the environment first, then from env_file (.env unless a subclass sets another, such as
    "../.env"), taken relative to load's folder. Unknown .env keys are rejected; immutable.
    Validation errors never echo a value, so a secret can't reach a log or the terminal."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=ENV_FILE, extra="forbid", frozen=True, hide_input_in_errors=True
    )

    @classmethod
    def load(cls, env_dir: Path) -> Self:
        """Read env_file relative to `env_dir`, not the working directory: an app started from
        the desktop menu runs in the home folder."""
        # None: the model reads no file
        env_file: DotenvType | None = cls.model_config.get("env_file")
        if env_file is None:
            return cls(_env_file=None)
        # str and Path first: a str is a Sequence too
        if isinstance(env_file, str | Path):
            return cls(_env_file=env_dir / env_file)
        return cls(_env_file=[env_dir / name for name in env_file])


class NoSecrets(BaseSecrets):
    """For apps that read no environment variables. It ignores any .env, so the app can run
    from a folder whose .env belongs to something else."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_file=None)


def load_secrets[TSecrets: BaseSecrets](model: type[TSecrets], env_dir: Path) -> TSecrets:
    try:
        return model.load(env_dir)
    except ValidationError as error:
        message: str = f"missing or invalid environment variables (see .env.example): {error}"
        raise ConfigError(message) from error
