from enum import StrEnum


class WebScheme(StrEnum):
    """URL schemes of the web. No third-party imports, so every extra can use it."""

    HTTP = "http"
    HTTPS = "https"
