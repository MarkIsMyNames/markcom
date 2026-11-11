import logging
from pathlib import Path
from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError


class ConfigError(Exception):
    """Config or environment is missing or invalid; the message names the key and its source."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class StrictModel(BaseModel):
    """Base for config and secrets: every field required, unknown keys rejected, immutable."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)


def _check_log_level(level: str) -> str:
    """Accept only the level names the standard logging library knows (DEBUG, INFO, WARNING...)."""
    if level not in logging.getLevelNamesMapping():
        unknown: str = f"unknown log level {level!r}"
        raise ValueError(unknown)
    return level


type LogLevel = Annotated[str, AfterValidator(_check_log_level)]


class BaseAppConfig(StrictModel):
    """Every app's config.json has at least a log level; subclass it to add the app's own keys."""

    log_level: LogLevel


def load_config[TConfig: StrictModel](path: Path, model: type[TConfig]) -> TConfig:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        missing: str = f"{path}: file not found"
        raise ConfigError(missing) from error
    except ValidationError as error:
        invalid: str = f"{path}: {error}"
        raise ConfigError(invalid) from error
