import logging
from pathlib import Path
from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError


class ConfigError(Exception): ...


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)


def _check_log_level(level: str) -> str:
    if level not in logging.getLevelNamesMapping():
        unknown: str = f"unknown log level {level!r}"
        raise ValueError(unknown)
    return level


type LogLevel = Annotated[str, AfterValidator(_check_log_level)]


def _check_log_format(log_format: str) -> str:
    sample: logging.LogRecord = logging.makeLogRecord({"msg": "sample"})
    # formatting a sample too: validate=True alone passes an unknown field or stray %
    try:
        logging.Formatter(log_format, validate=True).format(sample)
    except TypeError as error:
        raise ValueError(str(error)) from error
    return log_format


type LogFormat = Annotated[str, AfterValidator(_check_log_format)]


class BaseAppConfig(StrictModel):
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


CONFIG_PATH: Path = Path(__file__).with_name("config.json")

type HexColour = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
type Pixels = Annotated[int, Field(gt=0)]
type PixelGap = Annotated[int, Field(ge=0)]


class TrayConfig(StrictModel):
    icon_size: Pixels
    badge_size: Pixels
    badge_text_size: Pixels
    # panel clips a badge flush with the icon's edge
    badge_margin: PixelGap
    badge_colour: HexColour
    badge_text_colour: HexColour


class WindowConfig(StrictModel):
    width: Pixels
    height: Pixels


type Seconds = Annotated[float, Field(gt=0)]
type Count = Annotated[int, Field(ge=0)]


class UiServerConfig(StrictModel):
    shutdown_grace_sec: Count
    binding_refresh_sec: Seconds
    reconnect_timeout_sec: Seconds


class MarkcomConfig(StrictModel):
    log_format: LogFormat
    tray: TrayConfig
    window: WindowConfig
    ui_server: UiServerConfig


CONFIG: MarkcomConfig = load_config(CONFIG_PATH, MarkcomConfig)
