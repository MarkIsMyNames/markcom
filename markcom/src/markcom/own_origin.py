"""A loopback server's own address, and an ASGI guard that refuses every other Host or Origin.

Bound to loopback, a server is out of other machines' reach, but not of web pages in this
machine's browser: one could point a hostname of its own at 127.0.0.1 (DNS rebinding), or open
the server's websocket from another origin. Refusing a foreign Host, or Origin if there is one, on
every request, page and websocket alike, stops both.
"""

import logging
from enum import StrEnum
from http import HTTPStatus
from http.client import HTTP_PORT
from ipaddress import IPv4Address
from socket import INADDR_LOOPBACK

from pydantic import HttpUrl
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.status import WS_1008_POLICY_VIOLATION
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

logger: logging.Logger = logging.getLogger(__name__)

LOOPBACK: IPv4Address = IPv4Address(INADDR_LOOPBACK)
# What browsers also call LOOPBACK.
LOOPBACK_NAME: str = "localhost"
# Loopback only, so no TLS.
SCHEME: str = "http"
HOST_HEADER: str = "host"
ORIGIN_HEADER: str = "origin"


class ScopeType(StrEnum):
    """The ASGI scope types the guard checks; any other (lifespan) passes straight through."""

    HTTP = "http"
    WEBSOCKET = "websocket"


class InvalidPortError(ValueError): ...


def local_url(host: IPv4Address, port: int) -> HttpUrl:
    return HttpUrl(f"{SCHEME}://{host}:{port}/")


class OwnOriginOnly:
    """ASGI middleware: passes on only requests whose Host, and Origin if any, is host:port, or
    localhost:port when host is 127.0.0.1."""

    def __init__(self, app: ASGIApp, host: IPv4Address, port: int) -> None:
        if port < 1:
            # 0 asks the OS for any free port, which this guard can't know, so it'd refuse all
            invalid: str = f"port {port}: give the port the server listens on"
            raise InvalidPortError(invalid)
        names: list[str] = [str(host), LOOPBACK_NAME] if host == LOOPBACK else [str(host)]
        self._app: ASGIApp = app
        with_port: list[str] = [f"{name}:{port}" for name in names]
        # Browsers leave the default port out of Host and Origin.
        self._hosts: frozenset[str] = frozenset(
            [*with_port, *names] if port == HTTP_PORT else with_port
        )
        self._origins: frozenset[str] = frozenset(f"{SCHEME}://{h}" for h in self._hosts)
        logger.debug("accepting Host %s", sorted(self._hosts))

    def _allowed(self, scope: Scope) -> bool:
        headers: Headers = Headers(scope=scope)
        origin: str | None = headers.get(ORIGIN_HEADER)
        return headers.get(HOST_HEADER) in self._hosts and (
            origin is None or origin in self._origins
        )

    @staticmethod
    def _log_refusal(scope: Scope) -> None:
        headers: Headers = Headers(scope=scope)
        # %r: header values are untrusted, and repr keeps a CR or LF from forging a log line
        logger.warning(
            "refused %s from Host %r, Origin %r",
            scope["type"],
            headers.get(HOST_HEADER),
            headers.get(ORIGIN_HEADER),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == ScopeType.HTTP and not self._allowed(scope):
            self._log_refusal(scope)
            await PlainTextResponse(HTTPStatus.FORBIDDEN.phrase, HTTPStatus.FORBIDDEN)(
                scope, receive, send
            )
        elif scope["type"] == ScopeType.WEBSOCKET and not self._allowed(scope):
            self._log_refusal(scope)
            await WebSocketClose(WS_1008_POLICY_VIOLATION)(scope, receive, send)
        else:
            await self._app(scope, receive, send)
