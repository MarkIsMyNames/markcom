import logging
import sys
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path

from markcom.config import BaseAppConfig, ConfigError, load_config
from markcom.logs import configure_logging
from markcom.secrets import BaseSecrets, load_secrets

logger: logging.Logger = logging.getLogger(__name__)


class ExitCode(IntEnum):
    CONFIG_ERROR = 78


def run[TConfig: BaseAppConfig, TSecrets: BaseSecrets, TResult](
    main: Callable[[TConfig, TSecrets], TResult],
    config_path: Path,
    config_model: type[TConfig],
    secrets_model: type[TSecrets],
) -> TResult:
    """Entry point: config and secrets, then logging, then main. Exits non-zero on any failure."""
    try:
        config: TConfig = load_config(config_path, config_model)
        secrets: TSecrets = load_secrets(secrets_model, config_path.parent)
    except ConfigError as error:
        # Logging is not configured yet, so the error goes straight to stderr.
        sys.stderr.write(f"Configuration error: {error}\n")
        raise SystemExit(ExitCode.CONFIG_ERROR) from error
    configure_logging(config.log_level)
    # variable names only, never values
    logger.info(
        "Starting the app: configuration from %s, log level %s, environment variables %s",
        config_path,
        config.log_level,
        sorted(name.upper() for name in type(secrets).model_fields),
    )
    result: TResult = main(config, secrets)
    logger.info("The app returned")
    return result
