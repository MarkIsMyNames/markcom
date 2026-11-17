import multiprocessing
import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import HttpUrl
from PySide6.QtCore import QDeadlineTimer, QEventLoop, QObject, QPoint, QSize, QUrl, Slot
from PySide6.QtGui import QColor, QDesktopServices, QImage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QWidget

from markcom.window import WebWindow

# No display is needed: Qt draws off screen. CI runners block Chromium's namespace sandbox, and
# these tests load only pages they serve themselves.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

WAIT_MS = 5000
PUMP_MS = 50


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RecordingHandler(QuietHandler):
    requests = None

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
    handler = type("Handler", (RecordingHandler,), {"requests": requests})
    server, base = serve(folder, handler)
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
    app = QApplication(["window-test"])
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


@pytest.fixture
def make_window(request, site, icon):
    request.getfixturevalue("qt_app")
    windows = []

    def make():
        window = WebWindow("App", HttpUrl(f"{site}/index.html"), icon)
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.close()


def wait_until(predicate):
    deadline = QDeadlineTimer(WAIT_MS)
    while not predicate():
        if deadline.hasExpired():
            return False
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, PUMP_MS)
    return True


def visible_windows():
    return [w for w in QApplication.topLevelWidgets() if w.isVisible()]


def shown() -> QWidget:
    (window,) = visible_windows()
    return window


def view() -> QWebEngineView:
    return shown().findChild(QWebEngineView)


def click(link_id):
    view().page().runJavaScript(f"document.getElementById('{link_id}').click()")


def set_marker():
    view().page().runJavaScript("window.marker = 1")


def marker_reads_back():
    found = []
    view().page().runJavaScript("window.marker", found.append)
    return wait_until(lambda: found == [1])


def test_is_open_is_false_before_the_first_open(make_window):
    assert not make_window().is_open()


def test_close_before_the_first_open_does_nothing(make_window):
    window = make_window()
    window.close()
    assert not window.is_open()


def test_open_shows_the_page_under_the_title(make_window):
    window = make_window()
    window.open()
    assert window.is_open()
    assert shown().windowTitle() == "App"
    assert wait_until(lambda: view().title() == "Home")


def test_close_hides_the_window(make_window):
    window = make_window()
    window.open()
    window.close()
    assert not window.is_open()
    assert visible_windows() == []


def test_opening_twice_keeps_one_window_and_its_page(make_window):
    window = make_window()
    window.open()
    assert wait_until(lambda: view().title() == "Home")
    set_marker()
    window.open()
    assert len(visible_windows()) == 1
    assert marker_reads_back()


def test_reopening_keeps_size_position_and_page(make_window):
    window = make_window()
    window.open()
    assert wait_until(lambda: view().title() == "Home")
    shown().resize(640, 480)
    shown().move(100, 120)
    set_marker()
    window.close()
    window.open()
    assert shown().size() == QSize(640, 480)
    assert shown().pos() == QPoint(100, 120)
    assert marker_reads_back()


def test_open_and_close_from_another_thread_return_with_the_state_changed(make_window):
    window = make_window()
    records = []

    def work():
        window.open()
        records.append(window.is_open())
        window.close()
        records.append(window.is_open())

    thread = threading.Thread(target=work)
    thread.start()
    assert wait_until(lambda: not thread.is_alive())
    thread.join()
    assert records == [True, False]


def test_a_same_origin_link_loads_in_the_window(make_window, browser):
    make_window().open()
    assert wait_until(lambda: view().title() == "Home")
    click("same")
    assert wait_until(lambda: view().title() == "Two")
    assert browser.urls == []


def test_another_origin_opens_in_the_browser_not_the_window(make_window, browser):
    make_window().open()
    assert wait_until(lambda: view().title() == "Home")
    click("other")
    assert wait_until(lambda: browser.urls == ["https://example.org/x"])
    assert view().title() == "Home"


def test_a_new_window_link_to_another_origin_opens_in_the_browser(make_window, browser):
    make_window().open()
    assert wait_until(lambda: view().title() == "Home")
    click("other-new")
    assert wait_until(lambda: browser.urls == ["https://example.org/new"])
    assert view().title() == "Home"


def test_a_same_origin_new_window_link_loads_in_the_window(make_window, browser):
    make_window().open()
    assert wait_until(lambda: view().title() == "Home")
    click("same-new")
    assert wait_until(lambda: view().title() == "Two")
    assert browser.urls == []


@pytest.mark.parametrize("link_id", ["mail", "smb"])
def test_non_web_links_neither_load_nor_reach_the_desktop(make_window, browser, link_id):
    make_window().open()
    assert wait_until(lambda: view().title() == "Home")
    click(link_id)
    wait_until(lambda: False)
    assert browser.urls == []
    assert view().title() == "Home"


@pytest.mark.usefixtures("qt_app")
def test_another_origin_in_an_iframe_loads_in_the_page(browser, site, other_site, icon):
    window = WebWindow("App", HttpUrl(f"{site}/frame.html"), icon)
    try:
        window.open()
        assert wait_until(lambda: "/inner.html" in other_site[1])
        assert browser.urls == []
    finally:
        window.close()


def open_without_an_application(icon):
    """Child process body: no QApplication exists here, unlike in the test process."""
    window = WebWindow("App", HttpUrl("http://127.0.0.1:1/"), icon)
    try:
        window.open()
    except RuntimeError:
        sys.exit(3)


def test_methods_without_an_application_fail_fast(icon):
    # A fresh interpreter: this process already has the module's QApplication.
    child = multiprocessing.get_context("spawn").Process(
        target=open_without_an_application, args=(icon,)
    )
    child.start()
    child.join(60)
    assert child.exitcode == 3
