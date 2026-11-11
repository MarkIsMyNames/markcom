from typing import ClassVar

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from markcom.config import ConfigError

ENV_FILE: str = ".env"


class BaseSecrets(BaseSettings):
    """Base for secrets: each field is read from its upper-case variable (api_token: API_TOKEN),
    from the environment first, then from .env. Unknown .env keys are rejected; immutable."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=ENV_FILE, extra="forbid", frozen=True
    )


class NoSecrets(BaseSecrets):
    """For apps that read no environment variables."""


def load_secrets[TSecrets: BaseSecrets](model: type[TSecrets]) -> TSecrets:
    try:
        return model()
    except ValidationError as error:
        message: str = f"missing or invalid environment variables (see .env.example): {error}"
        raise ConfigError(message) from error
