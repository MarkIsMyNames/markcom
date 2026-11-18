import logging
import os
import threading
from contextlib import ExitStack
from typing import override

import pytest
from desktop_notifier import Urgency
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from markcom.config import CONFIG
from markcom.notifier import NEVER_EXPIRES_SEC
from markcom.tray import Tray, TrayAction, TrayNotifications, TrayTarget

# No display is needed: Qt draws off screen.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

WAIT_SEC = 2
app_log = logging.getLogger("app")


class SentNotifications(list):
    """DesktopNotifier stand-in: records each notification sent."""

    def send(self, title, message, urgency, display_sec):
        self.append((title, message, urgency, display_sec))


def noop():
    pass


class FakeWindow(TrayTarget):
    """Records each open/close and whether it ran on the GUI thread."""

    def __init__(self, *, is_open=False):
        self.opened = is_open
        self.calls = []
        self.on_main_thread = []

    @override
    def is_open(self):
        return self.opened

    @override
    def open(self):
        self._record("open", opened=True)

    @override
    def close(self):
        self._record("close", opened=False)

    def _record(self, call, *, opened):
        self.opened = opened
        self.calls.append(call)
        self.on_main_thread.append(threading.current_thread() is threading.main_thread())


@pytest.fixture
def make_tray(tmp_path):
    """Builds a tray on its own QApplication; both end with the test, as Qt allows one at a
    time."""
    icon = tmp_path / "icon.png"
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1565c0"))
    image.save(str(icon))
    with ExitStack() as stack:
        app = QApplication(["App"])
        stack.callback(app.shutdown)

        def make(notifier=None, target=None, actions=()):
            notifications = None if notifier is None else TrayNotifications(notifier, 8)
            return stack.enter_context(
                Tray(app, icon, notifications, target or FakeWindow(), actions)
            )

        yield make


def icon():
    (found,) = QApplication.instance().findChildren(QSystemTrayIcon)
    return found


def labels():
    return [a.text() for a in icon().contextMenu().actions() if not a.isSeparator()]


def test_menu_shows_the_actions_then_quit(make_tray):
    make_tray(actions=[TrayAction("Pause / resume", noop), TrayAction("Run", noop)])
    assert labels() == ["Pause / resume", "Run", "Quit"]
    assert icon().toolTip() == "App"


def left_click():
    icon().activated.emit(QSystemTrayIcon.ActivationReason.Trigger)


def test_left_click_opens_then_the_next_closes(make_tray):
    window = FakeWindow()
    make_tray(target=window)
    left_click()
    left_click()
    assert window.calls == ["open", "close"]


def test_left_click_runs_the_target_on_the_gui_thread(make_tray):
    window = FakeWindow()
    make_tray(target=window)
    left_click()
    assert window.on_main_thread == [True]


def test_left_click_closes_a_target_opened_outside_the_tray(make_tray):
    window = FakeWindow(is_open=True)
    make_tray(target=window)
    left_click()
    assert window.calls == ["close"]


def test_right_click_does_not_open(make_tray):
    window = FakeWindow()
    make_tray(target=window)
    icon().activated.emit(QSystemTrayIcon.ActivationReason.Context)
    assert window.calls == []


def test_menu_click_returns_before_a_slow_action_and_its_failure_is_contained(make_tray):
    release = threading.Event()
    done = threading.Event()

    def slow_then_fail():
        release.wait(WAIT_SEC)
        done.set()
        missing = "xdg-open missing"
        raise OSError(missing)

    make_tray(actions=[TrayAction("Open", slow_then_fail)])
    icon().contextMenu().actions()[0].trigger()
    assert not done.is_set()
    release.set()
    assert done.wait(WAIT_SEC)


def _has_badge():
    image = icon().icon().pixmap(64, 64).toImage().convertToFormat(QImage.Format.Format_RGB32)
    return any(
        image.pixelColor(x, y) == QColor(CONFIG.tray.badge_colour)
        for x in range(image.width())
        for y in range(image.height())
    )


def test_notifications_sent_through_the_tray_show_a_badge_until_a_left_click(make_tray):
    sent = SentNotifications()
    tray = make_tray(notifier=sent)
    assert not _has_badge()
    tray.send("feed", "down", Urgency.Critical, 8)
    tray.send("login", "down", Urgency.Critical, 8)
    QApplication.processEvents()
    assert sent == [("feed", "down", Urgency.Critical, 8), ("login", "down", Urgency.Critical, 8)]
    assert _has_badge()
    left_click()
    assert not _has_badge()


def test_a_tray_without_a_notifier_refuses_to_send(make_tray):
    tray = make_tray()
    with pytest.raises(RuntimeError):
        tray.send("t", "m", Urgency.Critical, 0)


def test_quit_ends_exec(make_tray):
    make_tray()
    QTimer.singleShot(0, icon().contextMenu().actions()[-1].trigger)
    QApplication.instance().exec()


def test_the_icon_shows_until_the_tray_is_left(tmp_path):
    icon_path = tmp_path / "icon.png"
    QImage(64, 64, QImage.Format.Format_ARGB32).save(str(icon_path))
    with ExitStack() as stack:
        app = QApplication(["App"])
        stack.callback(app.shutdown)
        with Tray(app, icon_path, None, FakeWindow(), ()):
            assert icon().isVisible()
        assert not icon().isVisible()


def test_the_tray_does_not_quit_when_its_last_window_closes(make_tray):
    make_tray()
    assert not QApplication.instance().quitOnLastWindowClosed()


@pytest.mark.parametrize(
    ("level", "urgency", "display_sec"),
    [
        (logging.ERROR, Urgency.Normal, 8),
        (logging.CRITICAL, Urgency.Critical, NEVER_EXPIRES_SEC),
    ],
)
def test_error_and_critical_records_are_sent(make_tray, level, urgency, display_sec):
    sent = SentNotifications()
    make_tray(notifier=sent)
    app_log.log(level, "cannot read %s", "feed")
    assert [(message, u, d) for _, message, u, d in sent] == [
        ("cannot read feed", urgency, display_sec)
    ]


def fail_with(error):
    raise error


@pytest.mark.parametrize(
    ("error", "body"),
    [
        pytest.param(
            OSError("connection refused"),
            "cannot read feed: OSError: connection refused",
            id="message",
        ),
        pytest.param(TimeoutError(), "cannot read feed: TimeoutError", id="no-message"),
        pytest.param(
            ExceptionGroup("2 reads failed", [OSError("refused"), TimeoutError("slow")]),
            "cannot read feed: ExceptionGroup: 2 reads failed (2 sub-exceptions)\n"
            "   OSError: refused\n"
            "   TimeoutError: slow",
            id="group",
        ),
    ],
)
def test_a_record_with_an_exception_shows_it_but_not_the_traceback(make_tray, error, body):
    sent = SentNotifications()
    make_tray(notifier=sent)
    try:
        fail_with(error)
    except (OSError, ExceptionGroup):
        app_log.exception("cannot read %s", "feed")
    assert [message for _, message, _, _ in sent] == [body]


@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO, logging.WARNING])
def test_records_below_error_are_not_sent(make_tray, level):
    sent = SentNotifications()
    make_tray(notifier=sent)
    app_log.log(level, "fine")
    assert sent == []


def test_a_repeated_error_is_sent_each_time(make_tray):
    sent = SentNotifications()
    make_tray(notifier=sent)
    app_log.error("down")
    app_log.error("down")
    assert len(sent) == 2


def test_a_tray_without_a_notifier_does_not_fail_on_error_records(make_tray):
    make_tray()
    app_log.error("down")


def test_records_are_not_sent_once_the_tray_is_left(tmp_path):
    icon_path = tmp_path / "icon.png"
    QImage(64, 64, QImage.Format.Format_ARGB32).save(str(icon_path))
    sent = SentNotifications()
    with ExitStack() as stack:
        app = QApplication(["App"])
        stack.callback(app.shutdown)
        with Tray(app, icon_path, TrayNotifications(sent, 8), FakeWindow(), ()):
            pass
        app_log.error("after")
    assert sent == []


class ArrivingNotifications(SentNotifications):
    """Also signals each arrival, for notifications sent from the tray's worker."""

    def __init__(self):
        super().__init__()
        self.arrived = threading.Event()

    def send(self, title, message, urgency, display_sec):
        super().send(title, message, urgency, display_sec)
        self.arrived.set()


@pytest.mark.parametrize("error", [KeyError("feed"), OSError("xdg-open missing")])
def test_a_failed_action_is_sent_as_one_notification(make_tray, error):
    sent = ArrivingNotifications()

    def broken():
        raise error

    make_tray(notifier=sent, actions=[TrayAction("Open", broken)])
    icon().contextMenu().actions()[0].trigger()
    assert sent.arrived.wait(WAIT_SEC)
    assert [urgency for _, _, urgency, _ in sent] == [Urgency.Normal]


class FailingNotifications:
    """DesktopNotifier stand-in with a bug: every send raises."""

    def send(self, *_):
        bug = "backend bug"
        raise TypeError(bug)


def test_a_failing_notifier_does_not_break_the_apps_logging(make_tray):
    make_tray(notifier=FailingNotifications())
    app_log.error("down")
