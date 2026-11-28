from enum import StrEnum

HOST_HEADER: str = "host"
ORIGIN_HEADER: str = "origin"


class WebProtocol(StrEnum):
    HTTP = "http"
    HTTPS = "https"
    WEBSOCKET = "websocket"
