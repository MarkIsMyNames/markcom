import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

from markcom.config import CONFIG, BaseAppConfig, ConfigError, load_config
from markcom.secrets import BaseSecrets, load_secrets

logger: logging.Logger = logging.getLogger(__name__)


def run[TConfig: BaseAppConfig, TSecrets: BaseSecrets, TResult](
    main: Callable[[TConfig, TSecrets], TResult],
    config_path: Path,
    config_model: type[TConfig],
    secrets_model: type[TSecrets],
) -> TResult:
    try:
        config: TConfig = load_config(config_path, config_model)
        secrets: TSecrets = load_secrets(secrets_model, config_path.parent)
    except ConfigError as error:
        # logging not configured yet
        sys.stderr.write(f"Configuration error: {error}\n")
        raise SystemExit(os.EX_CONFIG) from error
    # config sets the level, so logging comes after it
    logging.basicConfig(level=config.log_level, format=CONFIG.log_format, force=True)
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
