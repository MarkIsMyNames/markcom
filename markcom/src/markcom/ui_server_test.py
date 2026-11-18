import socket
import threading
from http import HTTPStatus

import httpx
import pytest
from nicegui import ui
from nicegui.testing import general

from markcom.own_origin import LOOPBACK
from markcom.ui_server import UiServer

# Seconds the server may take to stop.
STOP_WAIT_SEC = 5


@pytest.fixture(autouse=True)
def nicegui_globals():
    """Each test starts NiceGUI afresh, as a new process would."""
    with general.nicegui_reset_globals():
        yield


def root():
    ui.label("drawn by the root")


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_serves_the_root_on_loopback_and_refuses_a_foreign_host():
    port = free_port()
    with (
        UiServer(root, "App", LOOPBACK, port),
        httpx.Client(base_url=f"http://127.0.0.1:{port}") as browser,
    ):
        assert "drawn by the root" in browser.get("/").text
        foreign = browser.get("/", headers={"Host": "evil.example"})
        assert foreign.status_code == HTTPStatus.FORBIDDEN


def test_leaving_stops_the_server_with_a_browser_still_connected():
    port = free_port()
    left = threading.Event()

    def serve_then_leave():
        with (
            httpx.Client(base_url=f"http://127.0.0.1:{port}") as browser,
            UiServer(root, "App", LOOPBACK, port),
        ):
            browser.get("/")
        left.set()

    caller = threading.Thread(target=serve_then_leave, daemon=True)
    caller.start()
    caller.join(STOP_WAIT_SEC)
    assert left.is_set()
