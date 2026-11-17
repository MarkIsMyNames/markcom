import logging

from markcom.config import CONFIG, LogLevel


def configure_logging(level: LogLevel) -> None:
    """The one place logging is configured; runs after config loads, as config sets the level."""
    logging.basicConfig(level=level, format=CONFIG.log_format, force=True)
