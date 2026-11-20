import multiprocessing
import os
import signal
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import override

import pytest
from pydantic import HttpUrl
from PySide6.QtCore import QDeadlineTimer, QEventLoop, QMetaObject, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from markcom.window import WebWindow

# no display: Qt draws off screen. CI blocks Chromium's sandbox; tests load only their own
# pages. Window processes inherit both.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

# a window process starts Python, Qt and Chromium before it asks for the page
WAIT_MS = 30000
QUIET_MS = 1000
PUMP_MS = 50


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
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", requests
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    """Window processes save their size here, not in the real ~/.config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config"


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication(["window-test"])
    yield app
    app.shutdown()


@pytest.fixture
def icon(tmp_path):
    path = tmp_path / "icon.png"
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1565c0"))
    image.save(str(path))
    return path


@pytest.fixture
def page(site):
    base, requests = site
    requests.clear()
    return f"{base}/index.html", requests


@pytest.fixture
def make_window(request, page, icon):
    request.getfixturevalue("qt_app")
    windows = []

    def make():
        window = WebWindow("App", HttpUrl(page[0]), icon)
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.close()
    assert wait_until(lambda: window_processes() == [])


def wait_until(predicate, deadline_ms=WAIT_MS):
    deadline = QDeadlineTimer(deadline_ms)
    while not predicate():
        if deadline.hasExpired():
            return False
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, PUMP_MS)
    return True


def window_processes():
    """This test process's children running markcom.window_process."""
    found = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            stat = (process / "stat").read_text()
            command = (process / "cmdline").read_bytes()
        # ended while being read
        except (FileNotFoundError, ProcessLookupError):
            continue
        # stat: pid (command) state ppid; command may hold spaces
        parent = int(stat.rsplit(")", 1)[1].split()[1])
        if parent == os.getpid() and b"markcom.window_process" in command:
            found.append(process.name)
    return found


def test_is_open_is_false_before_the_first_open(make_window):
    assert not make_window().is_open()


def test_close_before_the_first_open_does_nothing(make_window):
    window = make_window()
    window.close()
    assert not window.is_open()
    assert window_processes() == []


def test_the_page_loads_on_the_first_open_not_before(make_window, page):
    window = make_window()
    wait_until(lambda: False, QUIET_MS)
    assert page[1] == []
    window.open()
    assert window.is_open()
    assert wait_until(lambda: "/index.html" in page[1])


def test_close_returns_once_the_window_process_has_ended(make_window, page):
    window = make_window()
    window.open()
    assert wait_until(lambda: "/index.html" in page[1])
    window.close()
    assert not window.is_open()
    assert window_processes() == []


def test_closing_the_window_saves_its_size(make_window, page, config_home):
    window = make_window()
    window.open()
    assert wait_until(lambda: "/index.html" in page[1])
    window.close()
    assert wait_until(lambda: window_processes() == [])
    assert (config_home / "markcom" / "App.conf").exists()


def test_a_window_whose_process_ends_by_itself_is_closed(make_window, page):
    window = make_window()
    window.open()
    assert wait_until(lambda: "/index.html" in page[1])
    (pid,) = window_processes()
    os.kill(int(pid), signal.SIGTERM)
    assert wait_until(lambda: not window.is_open())
    window.open()
    assert wait_until(lambda: page[1].count("/index.html") == 2)


def test_opening_twice_keeps_one_window_process(make_window, page):
    window = make_window()
    window.open()
    assert wait_until(lambda: "/index.html" in page[1])
    window.open()
    wait_until(lambda: False, QUIET_MS)
    assert window.is_open()
    assert len(window_processes()) == 1
    assert page[1].count("/index.html") == 1


def test_reopening_loads_the_page_afresh(make_window, page):
    window = make_window()
    window.open()
    assert wait_until(lambda: "/index.html" in page[1])
    window.close()
    window.open()
    assert window.is_open()
    assert wait_until(lambda: page[1].count("/index.html") == 2)


@pytest.mark.usefixtures("qt_app")
def test_the_page_address_is_not_on_the_window_processs_command_line(page, icon):
    window = WebWindow("App", HttpUrl(f"{page[0]}?token=SECRET"), icon)
    window.open()
    try:
        assert wait_until(lambda: any("token=SECRET" in path for path in page[1]))
        (pid,) = window_processes()
        assert b"SECRET" not in Path(f"/proc/{pid}/cmdline").read_bytes()
    finally:
        window.close()
        assert wait_until(lambda: window_processes() == [])


class QuitOnRequest(SimpleHTTPRequestHandler):
    """Quits the app once the window process asks for the page, so it has started."""

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
    """Child process: exits 0 only if its window process ended before the app did."""
    app = QApplication(["Quitting"])
    app.setQuitOnLastWindowClosed(False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuitOnRequest, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    WebWindow("Quitting", HttpUrl(url), icon).open()
    app.exec()
    server.shutdown()
    raise SystemExit(len(window_processes()))


def test_quitting_the_app_ends_an_open_windows_process_first(tmp_path, icon):
    (tmp_path / "index.html").write_text("<title>Home</title>", encoding="utf-8")
    child = multiprocessing.get_context("spawn").Process(
        target=run_an_app_that_quits_with_its_window_open, args=(tmp_path, icon)
    )
    child.start()
    try:
        child.join(60)
        assert child.exitcode == 0
    finally:
        if child.is_alive():
            child.kill()
            child.join()


def build_a_window_with_no_app(icon):
    """Child process: no QApplication, so none of the other tests' is present."""
    with pytest.raises(RuntimeError):
        WebWindow("Early", HttpUrl("http://127.0.0.1:9/"), icon)


def test_a_window_built_before_the_app_fails(icon):
    child = multiprocessing.get_context("spawn").Process(
        target=build_a_window_with_no_app, args=(icon,)
    )
    child.start()
    child.join(60)
    assert child.exitcode == 0


def run_a_window_without_a_tray(url, icon):
    """Child process: a QApplication of its own, as Qt allows one per process."""
    app = QApplication(["Solo"])
    window = WebWindow("Solo", HttpUrl(url), icon)
    window.open()
    # posted call runs once exec() starts
    QTimer.singleShot(0, window.close)
    app.exec()


def test_without_a_tray_closing_the_window_quits_the_app(page, icon):
    child = multiprocessing.get_context("spawn").Process(
        target=run_a_window_without_a_tray, args=(page[0], icon)
    )
    child.start()
    try:
        child.join(60)
        assert child.exitcode == 0
    finally:
        if child.is_alive():
            child.kill()
            child.join()
