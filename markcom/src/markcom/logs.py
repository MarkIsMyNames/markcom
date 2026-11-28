import logging

from markcom.config import CONFIG, LogLevel


def configure_logging(level: LogLevel) -> None:
    # force: replaces any handler a library set up on import
    logging.basicConfig(level=level, format=CONFIG.log_format, force=True)
