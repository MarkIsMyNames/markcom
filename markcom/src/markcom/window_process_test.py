import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple, override

import pytest
from PySide6.QtCore import QEvent, QObject, QSettings, QSize, QUrl, Slot
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPalette
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from markcom.config import CONFIG
from markcom.own_origin import LOOPBACK
from markcom.window_messages import WindowSpec
from markcom.window_process import OwnOriginWindow

# Qt draws off screen; no display. CI blocks Chromium sandbox; tests load only own pages.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
# offscreen has no GL: Chromium's GPU code crashes (SIGTRAP) soon after a page draws
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

QUIET_MS = 500
ANY_FREE_PORT = 0
CLOSED_PORT = 9  # discard port: nothing listens
ICON_PX = 64


class Site(NamedTuple):
    url: str
    requests: list


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
    server = ThreadingHTTPServer(
        (str(LOOPBACK), ANY_FREE_PORT), partial(handler, directory=str(folder))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _, port = server.server_address
    return server, f"http://{LOOPBACK}:{port}"


@pytest.fixture(scope="module")
def other_site(tmp_path_factory):
    folder = tmp_path_factory.mktemp("other")
    (folder / "inner.html").write_text("<title>Inner</title>", encoding="utf-8")
    requests = []

    class Handler(RecordingHandler):
        pass

    Handler.requests = requests
    server, base = serve(folder, Handler)
    yield Site(base, requests)
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
        f'<title>Frame</title><iframe src="{other_site.url}/inner.html"></iframe>',
        encoding="utf-8",
    )
    server, base = serve(folder, QuietHandler)
    yield base
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped: tray tests build own QApplication."""
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
    request.getfixturevalue("qapp")
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
    image = QImage(ICON_PX, ICON_PX, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1565c0"))
    image.save(str(path))
    return path


def spec_for(url, icon):
    return WindowSpec(
        title="App",
        url=url,
        icon=str(icon),
        width=CONFIG.window.width,
        height=CONFIG.window.height,
    )


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "window.conf"), QSettings.Format.IniFormat)


@pytest.fixture
def make_window(request, site, icon, settings):
    request.getfixturevalue("qapp")
    windows = []

    def make(page="index.html", base=site):
        window = OwnOriginWindow(spec_for(f"{base}/{page}", icon), settings)
        windows.append(window)
        return window

    yield make
    # Delete while QApplication lives: QtWebEngine aborts on page deleted after it.
    for window in windows:
        window.close()
        window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def view(window) -> QWebEngineView:
    return window.findChild(QWebEngineView)


def click(window, link_id):
    view(window).page().runJavaScript(f"document.getElementById('{link_id}').click()")


def shown_home(make_window, qtbot):
    window = make_window()
    qtbot.waitUntil(lambda: view(window).title() == "Home")
    return window


def test_the_window_shows_the_page_under_the_title(make_window, qtbot):
    window = make_window()
    assert window.windowTitle() == "App"
    qtbot.waitUntil(lambda: view(window).title() == "Home")


def test_the_window_stays_hidden_until_its_page_loads(make_window, qtbot):
    window = make_window()
    assert not window.isVisible()
    qtbot.waitUntil(window.isVisible)
    assert view(window).title() == "Home"


def test_a_page_that_fails_to_load_still_shows_the_window(make_window, qtbot):
    window = make_window(base=f"http://{LOOPBACK}:{CLOSED_PORT}")
    qtbot.waitUntil(window.isVisible)


@pytest.fixture
def dark_theme(qapp):
    theme = qapp.palette()
    dark = QPalette(theme)
    dark.setColor(QPalette.ColorRole.Base, QColor("#141618"))
    qapp.setPalette(dark)
    yield
    qapp.setPalette(theme)


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
    first.save_size()
    second = make_window()
    second.show()
    assert second.size() == QSize(640, 480)


def test_a_window_closed_maximised_comes_back_maximised(make_window):
    first = make_window()
    first.showMaximized()
    first.save_size()
    second = make_window()
    second.show()
    assert second.isMaximized()


def test_a_same_origin_link_loads_in_the_window(make_window, browser, qtbot):
    window = shown_home(make_window, qtbot)
    click(window, "same")
    qtbot.waitUntil(lambda: view(window).title() == "Two")
    assert browser.urls == []


def test_another_origin_opens_in_the_browser_not_the_window(make_window, browser, qtbot):
    window = shown_home(make_window, qtbot)
    click(window, "other")
    qtbot.waitUntil(lambda: browser.urls == ["https://example.org/x"])
    assert view(window).title() == "Home"


def test_a_new_window_link_to_another_origin_opens_in_the_browser(make_window, browser, qtbot):
    window = shown_home(make_window, qtbot)
    click(window, "other-new")
    qtbot.waitUntil(lambda: browser.urls == ["https://example.org/new"])
    assert view(window).title() == "Home"


def test_a_same_origin_new_window_link_loads_in_the_window(make_window, browser, qtbot):
    window = shown_home(make_window, qtbot)
    click(window, "same-new")
    qtbot.waitUntil(lambda: view(window).title() == "Two")
    assert browser.urls == []


@pytest.mark.parametrize("link_id", ["mail", "smb"])
def test_non_web_links_neither_load_nor_reach_the_desktop(make_window, browser, link_id, qtbot):
    window = shown_home(make_window, qtbot)
    click(window, link_id)
    qtbot.wait(QUIET_MS)
    assert browser.urls == []
    assert view(window).title() == "Home"


def test_another_origin_in_an_iframe_loads_in_the_page(make_window, browser, other_site, qtbot):
    make_window("frame.html")
    qtbot.waitUntil(lambda: "/inner.html" in other_site.requests)
    assert browser.urls == []
