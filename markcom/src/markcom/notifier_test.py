import platform
from pathlib import Path

import pytest
from desktop_notifier import Urgency

from markcom import notifier as notifier_module
from markcom.notifier import NEVER_EXPIRES_SEC, DesktopNotifier


class FakeBackend:
    """DesktopNotifierSync stand-in: records each send as (title, message, urgency, timeout)."""

    def __init__(self, sent, failure=None):
        self._sent = sent
        self._failure = failure

    def send(self, title, message, urgency, timeout):
        if self._failure is not None:
            raise self._failure
        self._sent.append((title, message, urgency, timeout))
        return title


@pytest.fixture
def sent(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    shown = []
    monkeypatch.setattr(notifier_module, "DesktopNotifierSync", lambda **_: FakeBackend(shown))
    return shown


def test_send_shows_for_the_display_time_given(sent):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, 8)
    assert sent == [("t", "m", Urgency.Normal, 8)]


def test_never_expires_sec_keeps_the_notification_until_dismissed(sent):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Critical, NEVER_EXPIRES_SEC)
    assert sent == [("t", "m", Urgency.Critical, 0)]


def test_unavailable_backend_makes_sends_do_nothing(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    def unavailable(**_):
        no_bus = "no bus"
        raise OSError(no_bus)

    monkeypatch.setattr(notifier_module, "DesktopNotifierSync", unavailable)
    notifier = DesktopNotifier("App", Path("app.png"))
    notifier.send("t", "m", Urgency.Normal, 8)
    notifier.send("t", "m", Urgency.Critical, 0)


def test_failed_send_is_not_raised(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        notifier_module,
        "DesktopNotifierSync",
        lambda **_: FakeBackend([], OSError("bus gone")),
    )
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, 8)


def test_programming_errors_are_not_hidden(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        notifier_module, "DesktopNotifierSync", lambda **_: FakeBackend([], KeyError("bug"))
    )
    notifier = DesktopNotifier("App", Path("app.png"))
    with pytest.raises(KeyError):
        notifier.send("t", "m", Urgency.Normal, 8)
