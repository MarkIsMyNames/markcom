import logging
from pathlib import Path
from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError


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


def _check_log_format(log_format: str) -> str:
    """Formatter(validate=True) alone passes an unknown field or a stray %."""
    sample: logging.LogRecord = logging.makeLogRecord({"msg": "sample"})
    try:
        logging.Formatter(log_format, validate=True).format(sample)
    except TypeError as error:
        raise ValueError(str(error)) from error
    return log_format


type LogFormat = Annotated[str, AfterValidator(_check_log_format)]


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


# markcom's own config, read from config.json beside this file. Apps never set these
CONFIG_PATH: Path = Path(__file__).with_name("config.json")

type HexColour = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
type Pixels = Annotated[int, Field(gt=0)]
type PixelGap = Annotated[int, Field(ge=0)]


class TrayConfig(StrictModel):
    """The tray icon and its unread badge, in pixels; the badge sits in the bottom-right corner."""

    # Edge of the icon the badge is drawn on; the desktop scales it to the panel.
    icon_size: Pixels
    # The badge's edge, in the icon's bottom-right corner, as messaging apps draw theirs.
    badge_size: Pixels
    # Its count's height.
    badge_text_size: Pixels
    # Gap between the badge and the icon's edge, so the panel does not clip it.
    badge_margin: PixelGap
    badge_colour: HexColour
    badge_text_colour: HexColour


class WindowConfig(StrictModel):
    """Web window's opening size; after that Qt keeps the user's."""

    width: Pixels
    height: Pixels


type Seconds = Annotated[float, Field(gt=0)]
type Count = Annotated[int, Field(ge=0)]


class UiServerConfig(StrictModel):
    """The NiceGUI server's settings that ui.run would otherwise take."""

    # Seconds open connections (the window's websocket) get to close on leaving.
    shutdown_grace_sec: Count
    # Seconds between NiceGUI's checks of bound values.
    binding_refresh_sec: Seconds
    reconnect_timeout_sec: Seconds
    message_history: Count


class MarkcomConfig(StrictModel):
    log_format: LogFormat
    # Names the app a written .desktop file belongs to, so no other file is ever taken over.
    desktop_entry_owner_key: str
    tray: TrayConfig
    window: WindowConfig
    ui_server: UiServerConfig


CONFIG: MarkcomConfig = load_config(CONFIG_PATH, MarkcomConfig)
