import contextlib
import multiprocessing
import os
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple, override

import psutil
import pytest
from pydantic import HttpUrl
from PySide6.QtCore import QMetaObject, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from markcom.own_origin import LOOPBACK
from markcom.window import WebWindow

# Qt draws off screen; no display. CI blocks Chromium sandbox; tests load only own pages.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
# offscreen has no GL: Chromium's GPU code crashes (SIGTRAP) soon after a page draws
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
# window processes inherit all three

# Window process starts Python, Qt and Chromium before asking for page.
WAIT_MS = 30000
QUIET_MS = 1000
CHILD_WAIT_SEC = 60
ANY_FREE_PORT = 0
CLOSED_PORT = 9  # discard port: nothing listens
ICON_PX = 64


class Page(NamedTuple):
    url: str
    requests: list


class RecordingHandler(SimpleHTTPRequestHandler):
    requests = None

    @override
    def log_message(self, *args):
        pass

    @override
    def do_GET(self):
        self.requests.append(self.path)
        super().do_GET()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    folder = tmp_path_factory.mktemp("site")
    (folder / "index.html").write_text("<title>Home</title>", encoding="utf-8")
    requests = []

    class Handler(RecordingHandler):
        pass

    Handler.requests = requests
    server = ThreadingHTTPServer(
        (str(LOOPBACK), ANY_FREE_PORT), partial(Handler, directory=str(folder))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _, port = server.server_address
    yield f"http://{LOOPBACK}:{port}", requests
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    """Window processes save size here, not real ~/.config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config"


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped: tray tests build own QApplication."""
    app = QApplication(["window-test"])
    yield app
    app.shutdown()


@pytest.fixture
def icon(tmp_path):
    path = tmp_path / "icon.png"
    image = QImage(ICON_PX, ICON_PX, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1565c0"))
    image.save(str(path))
    return path


@pytest.fixture
def page(site):
    base, requests = site
    requests.clear()
    return Page(f"{base}/index.html", requests)


@pytest.fixture
def make_window(request, page, icon):
    request.getfixturevalue("qapp")
    windows = []

    def make():
        window = WebWindow("App", HttpUrl(page.url), icon)
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.close()
    assert window_processes() == []


def window_processes():
    found = []
    for child in psutil.Process().children():
        # Process may end or be a zombie while read.
        with contextlib.suppress(psutil.NoSuchProcess):
            if "markcom.window_process" in " ".join(child.cmdline()):
                found.append(child)
    return found


def test_is_open_is_false_before_the_first_open(make_window):
    assert not make_window().is_open()


def test_close_before_the_first_open_does_nothing(make_window):
    window = make_window()
    window.close()
    assert not window.is_open()
    assert window_processes() == []


def test_the_page_loads_on_the_first_open_not_before(make_window, page, qtbot):
    window = make_window()
    qtbot.wait(QUIET_MS)
    assert page.requests == []
    window.open()
    assert window.is_open()
    qtbot.waitUntil(lambda: "/index.html" in page.requests, timeout=WAIT_MS)


def test_close_returns_once_the_window_process_has_ended(make_window, page, qtbot):
    window = make_window()
    window.open()
    qtbot.waitUntil(lambda: "/index.html" in page.requests, timeout=WAIT_MS)
    window.close()
    assert not window.is_open()
    assert window_processes() == []


def test_closing_the_window_saves_its_size(make_window, page, config_home, qtbot):
    window = make_window()
    window.open()
    qtbot.waitUntil(lambda: "/index.html" in page.requests, timeout=WAIT_MS)
    window.close()
    qtbot.waitUntil(lambda: window_processes() == [], timeout=WAIT_MS)
    assert (config_home / "markcom" / "App.conf").exists()


def test_a_window_whose_process_ends_by_itself_is_closed(make_window, page, qtbot):
    window = make_window()
    window.open()
    qtbot.waitUntil(lambda: "/index.html" in page.requests, timeout=WAIT_MS)
    (process,) = window_processes()
    process.terminate()
    qtbot.waitUntil(lambda: not window.is_open(), timeout=WAIT_MS)
    window.open()
    qtbot.waitUntil(lambda: page.requests.count("/index.html") == 2, timeout=WAIT_MS)


def test_opening_twice_keeps_one_window_process(make_window, page, qtbot):
    window = make_window()
    window.open()
    qtbot.waitUntil(lambda: "/index.html" in page.requests, timeout=WAIT_MS)
    window.open()
    qtbot.wait(QUIET_MS)
    assert window.is_open()
    assert len(window_processes()) == 1
    assert page.requests.count("/index.html") == 1


def test_reopening_loads_the_page_afresh(make_window, page, qtbot):
    window = make_window()
    window.open()
    qtbot.waitUntil(lambda: "/index.html" in page.requests, timeout=WAIT_MS)
    window.close()
    window.open()
    assert window.is_open()
    qtbot.waitUntil(lambda: page.requests.count("/index.html") == 2, timeout=WAIT_MS)


@pytest.mark.usefixtures("qapp")
def test_the_page_address_is_not_on_the_window_processs_command_line(page, icon, qtbot):
    window = WebWindow("App", HttpUrl(f"{page.url}?token=SECRET"), icon)
    window.open()
    try:
        qtbot.waitUntil(
            lambda: any("token=SECRET" in path for path in page.requests), timeout=WAIT_MS
        )
        (process,) = window_processes()
        assert "SECRET" not in " ".join(process.cmdline())
    finally:
        window.close()
        qtbot.waitUntil(lambda: window_processes() == [], timeout=WAIT_MS)


@pytest.fixture
def silent_server():
    server = socket.create_server((str(LOOPBACK), ANY_FREE_PORT))
    _, port = server.getsockname()
    accepted = []

    def accept():
        while True:
            try:
                connection, _ = server.accept()
                accepted.append(connection)
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    yield f"http://{LOOPBACK}:{port}/", accepted
    server.shutdown(socket.SHUT_RDWR)
    server.close()
    for connection in accepted:
        connection.close()


@pytest.mark.usefixtures("qapp")
def test_closing_before_the_page_loads_ends_the_process_cleanly(
    silent_server, icon, config_home, qtbot
):
    url, accepted = silent_server
    window = WebWindow("App", HttpUrl(url), icon)
    window.open()
    qtbot.waitUntil(lambda: accepted != [], timeout=WAIT_MS)
    window.close()
    assert window_processes() == []
    # Killed process saves nothing.
    assert (config_home / "markcom" / "App.conf").exists()


class QuitOnRequest(SimpleHTTPRequestHandler):
    """Quits app only once window process asks for page, so it has started."""

    @override
    def log_message(self, *args):
        pass

    @override
    def do_GET(self):
        super().do_GET()
        QMetaObject.invokeMethod(
            QApplication.instance(), "quit", Qt.ConnectionType.QueuedConnection
        )


def run_an_app_that_quits_with_its_window_open(folder, icon):
    """Child process; EX_OK only if its window process ended before app did."""
    app = QApplication(["Quitting"])
    app.setQuitOnLastWindowClosed(False)
    server = ThreadingHTTPServer(
        (str(LOOPBACK), ANY_FREE_PORT), partial(QuitOnRequest, directory=str(folder))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _, port = server.server_address
    url = f"http://{LOOPBACK}:{port}/index.html"
    WebWindow("Quitting", HttpUrl(url), icon).open()
    app.exec()
    server.shutdown()
    raise SystemExit(os.EX_OK if window_processes() == [] else os.EX_SOFTWARE)


def test_quitting_the_app_ends_an_open_windows_process_first(tmp_path, icon):
    (tmp_path / "index.html").write_text("<title>Home</title>", encoding="utf-8")
    child = multiprocessing.get_context("spawn").Process(
        target=run_an_app_that_quits_with_its_window_open, args=(tmp_path, icon)
    )
    child.start()
    try:
        child.join(CHILD_WAIT_SEC)
        assert child.exitcode == os.EX_OK
    finally:
        if child.is_alive():
            child.kill()
            child.join()


def build_a_window_with_no_app(icon):
    """Child process: other tests' QApplication absent."""
    with pytest.raises(RuntimeError):
        WebWindow("Early", HttpUrl(f"http://{LOOPBACK}:{CLOSED_PORT}/"), icon)


def test_a_window_built_before_the_app_fails(icon):
    child = multiprocessing.get_context("spawn").Process(
        target=build_a_window_with_no_app, args=(icon,)
    )
    child.start()
    child.join(CHILD_WAIT_SEC)
    assert child.exitcode == os.EX_OK


def run_a_window_without_a_tray(url, icon):
    """Child process: Qt allows one QApplication per process."""
    app = QApplication(["Solo"])
    window = WebWindow("Solo", HttpUrl(url), icon)
    window.open()
    # Posted call runs once exec() starts.
    QTimer.singleShot(0, window.close)
    app.exec()


def test_without_a_tray_closing_the_window_quits_the_app(page, icon):
    child = multiprocessing.get_context("spawn").Process(
        target=run_a_window_without_a_tray, args=(page.url, icon)
    )
    child.start()
    try:
        child.join(CHILD_WAIT_SEC)
        assert child.exitcode == os.EX_OK
    finally:
        if child.is_alive():
            child.kill()
            child.join()
