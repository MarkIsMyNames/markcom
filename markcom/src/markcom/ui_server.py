"""Not ui.run(): it blocks the main thread, which tray and window need. uvicorn on a thread."""

import logging
import threading
from collections.abc import Callable
from ipaddress import IPv4Address
from socket import socket
from typing import Self

import uvicorn
from nicegui import core
from pydantic import HttpUrl

from markcom.config import CONFIG
from markcom.own_origin import OwnOriginOnly, local_url

logger: logging.Logger = logging.getLogger(__name__)

WEBSOCKETS: str = "wsproto"
# ui.run's default; not config, as QtWebEngine and desktop browsers ignore the viewport tag
VIEWPORT: str = "width=device-width, initial-scale=1"
# ui.run's default; resends after the websocket drops on suspend and resume
MESSAGE_HISTORY: int = 1000


def configure(root: Callable[[], None], title: str) -> None:
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


class UiServer:
    def __init__(self, root: Callable[[], None], title: str, host: IPv4Address, port: int) -> None:
        configure(root, title)
        self._title: str = title
        self._url: HttpUrl = local_url(host, port)
        settings: uvicorn.Config = uvicorn.Config(
            OwnOriginOnly(core.app, host, port),
            host=str(host),
            port=port,
            log_config=None,
            # None: uvicorn follows config.json's level; INFO logs request paths and queries,
            # NiceGUI's client_id among them
            log_level=None,
            ws=WEBSOCKETS,
            timeout_graceful_shutdown=CONFIG.ui_server.shutdown_grace_sec,
        )
        # bound on the caller's thread, so a port in use fails the start, not a background thread
        self._socket: socket = settings.bind_socket()
        # bind_socket doesn't listen; uvicorn would on its thread, refusing connections until then
        self._socket.listen()
        logger.debug("listening on %s", self._socket.getsockname())
        self._server: uvicorn.Server = uvicorn.Server(settings)
        self._thread: threading.Thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._socket]}, name="ui"
        )

    def __enter__(self) -> Self:
        self._thread.start()
        logger.info("serving %r at %s", self._title, self._url)
        return self

    def __exit__(self, *_: object) -> None:
        logger.info("stopping %r", self._title)
        self._server.should_exit = True
        self._thread.join()
        self._socket.close()
        logger.info("stopped %r", self._title)
