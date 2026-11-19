"""Names from the web's protocols. No third-party imports, so every extra can use them."""

from enum import StrEnum

HOST_HEADER: str = "host"
ORIGIN_HEADER: str = "origin"


class WebProtocol(StrEnum):
    """Web protocols, by the names URL schemes (http, https) and ASGI scope types (http,
    websocket) give them."""

    HTTP = "http"
    HTTPS = "https"
    WEBSOCKET = "websocket"
