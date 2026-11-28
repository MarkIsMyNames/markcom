from pathlib import Path
from typing import ClassVar, Final, Self

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotenvType

from markcom.config import ConfigError

ENV_FILE: str = ".env"
# Final: mypy takes literal key and keeps model_config's value type
ENV_FILE_KEY: Final = "env_file"


class BaseSecrets(BaseSettings):
    # hide_input_in_errors: a secret must never reach a log or terminal
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=ENV_FILE, extra="forbid", frozen=True, hide_input_in_errors=True
    )

    @classmethod
    def load(cls, env_dir: Path) -> Self:
        # not the working directory: an app started from the desktop menu runs in home
        env_file: DotenvType | None = cls.model_config.get(ENV_FILE_KEY)
        if env_file is None:
            return cls()
        if not isinstance(env_file, str | Path):
            several: str = f"{cls.__name__}: env_file must name one file, not {env_file}"
            raise TypeError(several)
        return cls(_env_file=env_dir / env_file)


class NoSecrets(BaseSecrets):
    # env_file None: a .env in the folder may belong to something else
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_file=None)


def load_secrets[TSecrets: BaseSecrets](model: type[TSecrets], env_dir: Path) -> TSecrets:
    try:
        return model.load(env_dir)
    except ValidationError as error:
        message: str = f"missing or invalid environment variables (see .env.example): {error}"
        raise ConfigError(message) from error
