"""A NiceGUI UI served by uvicorn on its own thread, behind the own-origin guard.

ui.run() would block the main thread, which markcom's tray and window need, so this does what it
does for a UI shown in that window (no reload, no browser tab, no native window of NiceGUI's own)
and runs uvicorn on a thread. uvicorn only installs signal handlers on the main thread, so on this
one it leaves them alone.
"""

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from ipaddress import IPv4Address
from socket import socket
from typing import Self, override

import uvicorn
from nicegui import core

from markcom.own_origin import OwnOriginOnly

# Seconds open connections (the window's websocket) get to close on leaving.
SHUTDOWN_GRACE_SEC: int = 1
LOG_LEVEL: str = "warning"
# The websocket implementation NiceGUI runs on.
WEBSOCKETS: str = "wsproto"
VIEWPORT: str = "width=device-width, initial-scale=1"
# Seconds between NiceGUI's checks of bound values.
BINDING_REFRESH_SEC: float = 0.5
RECONNECT_TIMEOUT_SEC: float = 3.0
MESSAGE_HISTORY: int = 1000


def configure(root: Callable[[], None], title: str) -> None:
    """Make `root` build every page, with the settings ui.run would give it."""
    core.app.config.add_run_config(
        reload=False,
        title=title,
        viewport=VIEWPORT,
        favicon=None,
        dark=None,
        language=None,
        binding_refresh_interval=BINDING_REFRESH_SEC,
        reconnect_timeout=RECONNECT_TIMEOUT_SEC,
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
        settings: uvicorn.Config = uvicorn.Config(
            OwnOriginOnly(core.app, host, port),
            host=str(host),
            port=port,
            # Leave the app's logging set up as it is.
            log_config=None,
            log_level=LOG_LEVEL,
            ws=WEBSOCKETS,
            timeout_graceful_shutdown=SHUTDOWN_GRACE_SEC,
        )
        self._socket: socket = settings.bind_socket()
        self._server: uvicorn.Server = uvicorn.Server(settings)
        self._thread: threading.Thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._socket]}, name="ui"
        )

    @override
    def __enter__(self) -> Self:
        self._thread.start()
        return self

    @override
    def __exit__(self, *_: object) -> None:
        self._server.should_exit = True
        self._thread.join()
        self._socket.close()
