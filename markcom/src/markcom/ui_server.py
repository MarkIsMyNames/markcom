"""A NiceGUI UI served by uvicorn on its own thread, behind the own-origin guard.

ui.run() would block the main thread, which markcom's tray and window need, so this does what it
does for a UI shown in that window (no reload, no browser tab, no native window of NiceGUI's own)
and runs uvicorn on a thread. uvicorn only installs signal handlers on the main thread, so on this
one it leaves them alone.
"""

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from ipaddress import IPv4Address
from socket import socket
from typing import Self, override

import uvicorn
from nicegui import core
from pydantic import HttpUrl

from markcom.config import CONFIG
from markcom.own_origin import OwnOriginOnly, local_url

logger: logging.Logger = logging.getLogger(__name__)

# The websocket implementation NiceGUI runs on.
WEBSOCKETS: str = "wsproto"
# ui.run's default. Not config: QtWebEngine and desktop browsers ignore the viewport meta tag.
VIEWPORT: str = "width=device-width, initial-scale=1"
# ui.run's default: messages kept to resend after the websocket drops (suspend and resume).
MESSAGE_HISTORY: int = 1000


def configure(root: Callable[[], None], title: str) -> None:
    """Make `root` build every page, with the settings ui.run would give it."""
    logger.debug("NiceGUI configured for %r", title)
    core.app.config.add_run_config(
        reload=False,
        title=title,
        viewport=VIEWPORT,
        favicon=None,
        dark=None,
        language=None,
        binding_refresh_interval=CONFIG.ui_server.binding_refresh_sec,
        reconnect_timeout=CONFIG.ui_server.reconnect_timeout_sec,
        message_history_length=MESSAGE_HISTORY,
        tailwind=True,
        unocss=None,
        prod_js=True,
        show_welcome_message=False,
        markdown=False,
    )
    core.root = root


class UiServer(AbstractContextManager["UiServer"]):
    """Entering starts serving on a thread; leaving tells uvicorn to stop, which closes every
    connection, and joins the thread.

    The socket is bound here, on the caller's thread, so a port already in use fails the start
    rather than a background thread.
    """

    def __init__(self, root: Callable[[], None], title: str, host: IPv4Address, port: int) -> None:
        configure(root, title)
        self._title: str = title
        self._url: HttpUrl = local_url(host, port)
        settings: uvicorn.Config = uvicorn.Config(
            OwnOriginOnly(core.app, host, port),
            host=str(host),
            port=port,
            # Leave the app's logging set up as it is.
            log_config=None,
            # None: uvicorn's loggers follow config.json's level; at INFO they log request
            # paths and queries, NiceGUI's client_id among them
            log_level=None,
            ws=WEBSOCKETS,
            timeout_graceful_shutdown=CONFIG.ui_server.shutdown_grace_sec,
        )
        self._socket: socket = settings.bind_socket()
        # bind_socket doesn't listen; uvicorn would on its thread, refusing connections until then
        self._socket.listen()
        logger.debug("listening on %s", self._socket.getsockname())
        self._server: uvicorn.Server = uvicorn.Server(settings)
        self._thread: threading.Thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._socket]}, name="ui"
        )

    @override
    def __enter__(self) -> Self:
        self._thread.start()
        logger.info("serving %r at %s", self._title, self._url)
        return self

    @override
    def __exit__(self, *_: object) -> None:
        logger.info("stopping %r", self._title)
        self._server.should_exit = True
        self._thread.join()
        self._socket.close()
        logger.info("stopped %r", self._title)
