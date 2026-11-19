"""Names from the web's protocols. No third-party imports, so every extra can use them."""

from enum import StrEnum

HOST_HEADER: str = "host"
ORIGIN_HEADER: str = "origin"


class WebScheme(StrEnum):
    """URL schemes of the web."""

    HTTP = "http"
    HTTPS = "https"


class ScopeType(StrEnum):
    """The ASGI scope types the guard checks; any other (lifespan) passes straight through."""

    HTTP = "http"
    WEBSOCKET = "websocket"
