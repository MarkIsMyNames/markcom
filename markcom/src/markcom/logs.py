import logging

from markcom.config import LogLevel

LOG_FORMAT: str = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: LogLevel) -> None:
    """The one place logging is configured; runs after config loads, as config sets the level."""
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
