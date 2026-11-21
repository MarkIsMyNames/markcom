import asyncio
import threading
from pathlib import Path

import desktop_notifier
import pytest
from desktop_notifier import Urgency

from markcom.notifier import NEVER_EXPIRES_SEC, DesktopNotifier


class FakeNotifier:
    """desktop-notifier stand-in: records each send as (title, message, urgency, timeout) after
    yielding once, so a caller that didn't wait finds nothing yet."""

    def __init__(self, sent, failure=None):
        self.sent = sent
        self._failure = failure

    def __call__(self, *, app_icon, **_):
        self.app_icon = app_icon
        return self

    async def send(self, **fields):
        await asyncio.sleep(0)
        if self._failure is not None:
            raise self._failure
        self.sent.append((fields["title"], fields["message"], fields["urgency"], fields["timeout"]))


@pytest.fixture
def library(monkeypatch):
    fake = FakeNotifier([])
    monkeypatch.setattr(desktop_notifier, "DesktopNotifier", fake)
    return fake


def test_send_returns_once_shown_for_the_display_time_given(library):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, 8)
    assert library.sent == [("t", "m", Urgency.Normal, 8)]


def test_never_expires_sec_keeps_the_notification_until_dismissed(library):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Critical, NEVER_EXPIRES_SEC)
    assert library.sent == [("t", "m", Urgency.Critical, 0)]


def test_a_relative_icon_reaches_the_desktop_as_an_absolute_path(library):
    DesktopNotifier("App", Path("app.png"))
    assert library.app_icon.path == Path("app.png").resolve()


def test_sends_from_two_threads_at_once_both_arrive(library):
    notifier = DesktopNotifier("App", Path("app.png"))
    senders = [
        threading.Thread(target=notifier.send, args=(title, "m", Urgency.Normal, 8))
        for title in ("a", "b")
    ]
    for sender in senders:
        sender.start()
    for sender in senders:
        sender.join()
    assert sorted(title for title, *_ in library.sent) == ["a", "b"]


async def test_a_send_from_inside_a_running_event_loop_arrives(library):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, 8)
    assert library.sent == [("t", "m", Urgency.Normal, 8)]


def test_programming_errors_are_not_hidden(monkeypatch):
    monkeypatch.setattr(desktop_notifier, "DesktopNotifier", FakeNotifier([], KeyError("bug")))
    notifier = DesktopNotifier("App", Path("app.png"))
    with pytest.raises(KeyError):
        notifier.send("t", "m", Urgency.Normal, 8)


@pytest.mark.parametrize("error", [RuntimeError("no toast manager"), OSError("registry")])
def test_an_unavailable_notifier_makes_sends_do_nothing(monkeypatch, error):
    def unavailable(**_):
        raise error

    monkeypatch.setattr(desktop_notifier, "DesktopNotifier", unavailable)
    notifier = DesktopNotifier("App", Path("app.png"))
    notifier.send("t", "m", Urgency.Normal, 8)
