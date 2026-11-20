import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import override

import pytest
from pydantic import HttpUrl
from PySide6.QtCore import QDeadlineTimer, QEvent, QEventLoop, QObject, QSettings, QSize, QUrl, Slot
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPalette
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from markcom.config import CONFIG
from markcom.window_messages import WindowSpec
from markcom.window_process import CloseOnEndOfInput, OwnOriginWindow

# no display: Qt draws off screen. CI blocks Chromium's sandbox; tests load only their own
# pages.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

WAIT_MS = 5000
QUIET_MS = 500
PUMP_MS = 50


class QuietHandler(SimpleHTTPRequestHandler):
    @override
    def log_message(self, *args):
        pass


class RecordingHandler(QuietHandler):
    requests = None

    @override
    def do_GET(self):
        self.requests.append(self.path)
        super().do_GET()


def serve(folder, handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture(scope="module")
def other_site(tmp_path_factory):
    folder = tmp_path_factory.mktemp("other")
    (folder / "inner.html").write_text("<title>Inner</title>", encoding="utf-8")
    requests = []

    class Handler(RecordingHandler):
        pass

    Handler.requests = requests
    server, base = serve(folder, Handler)
    yield base, requests
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def site(tmp_path_factory, other_site):
    folder = tmp_path_factory.mktemp("site")
    links = (
        '<a id=same href="/two.html">s</a>'
        '<a id=other href="https://example.org/x">o</a>'
        '<a id=other-new target=_blank href="https://example.org/new">n</a>'
        '<a id=same-new target=_blank href="/two.html">m</a>'
        '<a id=mail href="mailto:a@example.org">a</a>'
        '<a id=smb href="smb://fileserver/share">f</a>'
    )
    (folder / "index.html").write_text(f"<title>Home</title>{links}", encoding="utf-8")
    (folder / "two.html").write_text("<title>Two</title>", encoding="utf-8")
    (folder / "frame.html").write_text(
        f'<title>Frame</title><iframe src="{other_site[0]}/inner.html"></iframe>',
        encoding="utf-8",
    )
    server, base = serve(folder, QuietHandler)
    yield base
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication(["window-process-test"])
    yield app
    app.shutdown()


class Browser(QObject):
    def __init__(self):
        super().__init__()
        self.urls = []

    @Slot(QUrl)
    def record(self, url):
        self.urls.append(url.toString())


@pytest.fixture
def browser(request):
    request.getfixturevalue("qt_app")
    recorder = Browser()
    schemes = ("https", "mailto", "smb")
    for scheme in schemes:
        QDesktopServices.setUrlHandler(scheme, recorder, "record")
    yield recorder
    for scheme in schemes:
        QDesktopServices.unsetUrlHandler(scheme)


@pytest.fixture
def icon(tmp_path):
    path = tmp_path / "icon.png"
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1565c0"))
    image.save(str(path))
    return path


def spec_for(url, icon):
    return WindowSpec(title="App", url=HttpUrl(url), icon=Path(icon), log_level="WARNING")


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "window.conf"), QSettings.Format.IniFormat)


@pytest.fixture
def make_window(request, site, icon, settings):
    request.getfixturevalue("qt_app")
    windows = []

    def make(page="index.html"):
        window = OwnOriginWindow(spec_for(f"{site}/{page}", icon), settings)
        windows.append(window)
        return window

    yield make
    # deleted now, while their QApplication lives: QtWebEngine aborts on a page deleted after it
    for window in windows:
        window.close()
        window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wait_until(predicate, deadline_ms=WAIT_MS):
    deadline = QDeadlineTimer(deadline_ms)
    while not predicate():
        if deadline.hasExpired():
            return False
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, PUMP_MS)
    return True


def view(window) -> QWebEngineView:
    return window.findChild(QWebEngineView)


def click(window, link_id):
    view(window).page().runJavaScript(f"document.getElementById('{link_id}').click()")


def shown_home(make_window):
    window = make_window()
    window.show()
    assert wait_until(lambda: view(window).title() == "Home")
    return window


def test_the_window_shows_the_page_under_the_title(make_window):
    window = make_window()
    window.show()
    assert window.windowTitle() == "App"
    assert wait_until(lambda: view(window).title() == "Home")


@pytest.fixture
def dark_theme(qt_app):
    theme = qt_app.palette()
    dark = QPalette(theme)
    dark.setColor(QPalette.ColorRole.Base, QColor("#141618"))
    qt_app.setPalette(dark)
    yield
    qt_app.setPalette(theme)


@pytest.mark.usefixtures("dark_theme")
def test_until_the_page_draws_the_window_shows_the_themes_content_colour(make_window):
    window = make_window()
    assert view(window).page().backgroundColor() == QColor("#141618")


def test_a_first_window_opens_at_the_configured_size(make_window):
    window = make_window()
    window.show()
    assert window.size() == QSize(CONFIG.window.width, CONFIG.window.height)


def test_the_next_window_takes_the_last_ones_size(make_window):
    first = make_window()
    first.show()
    first.resize(640, 480)
    first.close()
    second = make_window()
    second.show()
    assert second.size() == QSize(640, 480)


def test_a_window_closed_maximised_comes_back_maximised(make_window):
    first = make_window()
    first.showMaximized()
    first.close()
    second = make_window()
    second.show()
    assert second.isMaximized()


def test_a_same_origin_link_loads_in_the_window(make_window, browser):
    window = shown_home(make_window)
    click(window, "same")
    assert wait_until(lambda: view(window).title() == "Two")
    assert browser.urls == []


def test_another_origin_opens_in_the_browser_not_the_window(make_window, browser):
    window = shown_home(make_window)
    click(window, "other")
    assert wait_until(lambda: browser.urls == ["https://example.org/x"])
    assert view(window).title() == "Home"


def test_a_new_window_link_to_another_origin_opens_in_the_browser(make_window, browser):
    window = shown_home(make_window)
    click(window, "other-new")
    assert wait_until(lambda: browser.urls == ["https://example.org/new"])
    assert view(window).title() == "Home"


def test_a_same_origin_new_window_link_loads_in_the_window(make_window, browser):
    window = shown_home(make_window)
    click(window, "same-new")
    assert wait_until(lambda: view(window).title() == "Two")
    assert browser.urls == []


@pytest.mark.parametrize("link_id", ["mail", "smb"])
def test_non_web_links_neither_load_nor_reach_the_desktop(make_window, browser, link_id):
    window = shown_home(make_window)
    click(window, link_id)
    wait_until(lambda: False, QUIET_MS)
    assert browser.urls == []
    assert view(window).title() == "Home"


def test_another_origin_in_an_iframe_loads_in_the_page(make_window, browser, other_site):
    make_window("frame.html").show()
    assert wait_until(lambda: "/inner.html" in other_site[1])
    assert browser.urls == []


@pytest.fixture
def pipe():
    read_end, write_end = os.pipe()
    with os.fdopen(read_end, "rb", buffering=0) as reader, os.fdopen(write_end, "wb", 0) as writer:
        yield reader, writer


def test_the_end_of_input_closes_the_window(make_window, pipe):
    reader, writer = pipe
    window = make_window()
    CloseOnEndOfInput(reader.fileno(), window)
    window.show()
    writer.close()
    assert wait_until(lambda: not window.isVisible())
