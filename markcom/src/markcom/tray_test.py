import os
import threading
from contextlib import ExitStack

import pytest
from desktop_notifier import Urgency
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from markcom.config import CONFIG
from markcom.tray import Tray, TrayAction

# No display is needed: Qt draws off screen.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

WAIT_SEC = 2


class SentNotifications(list):
    """DesktopNotifier stand-in: records each notification sent."""

    def send(self, title, message, urgency, display_sec):
        self.append((title, message, urgency, display_sec))


def noop():
    pass


@pytest.fixture
def make_tray(tmp_path):
    """Builds a tray, entered for the test and left after it; each test gets its own, which
    also shows that leaving a tray releases Qt's one application."""
    icon = tmp_path / "icon.png"
    # A QImage, as a QPixmap needs the application the tray makes.
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1565c0"))
    image.save(str(icon))
    with ExitStack() as stack:

        def make(notifier=None, on_click=noop, actions=()):
            return stack.enter_context(Tray("App", icon, notifier, on_click, actions))

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


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (QSystemTrayIcon.ActivationReason.Trigger, True),
        (QSystemTrayIcon.ActivationReason.Context, False),
    ],
)
def test_left_click_runs_the_click_action_and_right_click_does_not(make_tray, reason, expected):
    ran = threading.Event()
    make_tray(on_click=ran.set)
    icon().activated.emit(reason)
    assert ran.wait(WAIT_SEC if expected else 0.2) is expected


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
    icon().activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert not _has_badge()


def test_a_tray_without_a_notifier_refuses_to_send(make_tray):
    tray = make_tray()
    with pytest.raises(RuntimeError):
        tray.send("t", "m", Urgency.Critical, 0)


def test_quit_ends_run(make_tray):
    tray = make_tray()
    QTimer.singleShot(0, icon().contextMenu().actions()[-1].trigger)
    tray.run()
