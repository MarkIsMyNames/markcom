"""A loopback server's own address, and an ASGI guard that refuses every other Host or Origin.

Bound to loopback, a server is out of other machines' reach, but not of web pages in this
machine's browser: one could point a hostname of its own at 127.0.0.1 (DNS rebinding), or open
the server's websocket from another origin. Refusing a foreign Host, or Origin if there is one, on
every request, page and websocket alike, stops both.
"""

from http import HTTPStatus
from ipaddress import IPv4Address

from pydantic import HttpUrl
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.status import WS_1008_POLICY_VIOLATION
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

LOOPBACK: IPv4Address = IPv4Address("127.0.0.1")
# What browsers also call LOOPBACK.
LOOPBACK_NAME: str = "localhost"
# Loopback only, so no TLS.
SCHEME: str = "http"
FORBIDDEN: str = "Forbidden"


def local_url(host: IPv4Address, port: int) -> HttpUrl:
    return HttpUrl(f"{SCHEME}://{host}:{port}/")


class OwnOriginOnly:
    """ASGI middleware: passes on only requests whose Host, and Origin if any, is host:port, or
    localhost:port when host is 127.0.0.1."""

    def __init__(self, app: ASGIApp, host: IPv4Address, port: int) -> None:
        names: list[str] = [str(host), LOOPBACK_NAME] if host == LOOPBACK else [str(host)]
        self._app: ASGIApp = app
        self._hosts: frozenset[str] = frozenset(f"{name}:{port}" for name in names)
        self._origins: frozenset[str] = frozenset(f"{SCHEME}://{h}" for h in self._hosts)

    def _allowed(self, scope: Scope) -> bool:
        headers: Headers = Headers(scope=scope)
        origin: str | None = headers.get("origin")
        return headers.get("host") in self._hosts and (origin is None or origin in self._origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self._allowed(scope):
            await PlainTextResponse(FORBIDDEN, HTTPStatus.FORBIDDEN)(scope, receive, send)
        elif scope["type"] == "websocket" and not self._allowed(scope):
            await WebSocketClose(WS_1008_POLICY_VIOLATION)(scope, receive, send)
        else:
            await self._app(scope, receive, send)
