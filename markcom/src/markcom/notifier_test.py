import asyncio
import queue
import threading
from pathlib import Path

import desktop_notifier
import pytest
from desktop_notifier import Urgency

from markcom.notifier import NEVER_EXPIRES_SEC, DesktopNotifier

DISPLAY_SEC = 8
WAIT_SEC = 5


class FakeNotifier:
    """Fails the first `failures` sends, then queues each one."""

    def __init__(self, failures=0):
        self.sent = queue.Queue()
        self._failures = failures

    def __call__(self, *, app_icon, **_):
        self.app_icon = app_icon
        return self

    async def send(self, **fields):
        await asyncio.sleep(0)
        if self._failures:
            self._failures -= 1
            bug = "bug"
            raise KeyError(bug)
        self.sent.put((fields["title"], fields["message"], fields["urgency"], fields["timeout"]))

    def next_sent(self):
        return self.sent.get(timeout=WAIT_SEC)


@pytest.fixture
def library(monkeypatch):
    fake = FakeNotifier()
    monkeypatch.setattr(desktop_notifier, "DesktopNotifier", fake)
    return fake


def test_send_shows_it_for_the_display_time_given(library):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, DISPLAY_SEC)
    assert library.next_sent() == ("t", "m", Urgency.Normal, DISPLAY_SEC)


def test_never_expires_sec_keeps_the_notification_until_dismissed(library):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Critical, NEVER_EXPIRES_SEC)
    assert library.next_sent() == ("t", "m", Urgency.Critical, NEVER_EXPIRES_SEC)


def test_a_relative_icon_reaches_the_desktop_as_an_absolute_path(library):
    DesktopNotifier("App", Path("app.png"))
    assert library.app_icon.path == Path("app.png").resolve()


def test_sends_from_two_threads_at_once_both_arrive(library):
    notifier = DesktopNotifier("App", Path("app.png"))
    senders = [
        threading.Thread(target=notifier.send, args=(title, "m", Urgency.Normal, DISPLAY_SEC))
        for title in ("a", "b")
    ]
    for sender in senders:
        sender.start()
    for sender in senders:
        sender.join()
    assert sorted(library.next_sent()[0] for _ in senders) == ["a", "b"]


async def test_a_send_from_inside_a_running_event_loop_arrives(library):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, DISPLAY_SEC)
    assert await asyncio.to_thread(library.next_sent) == ("t", "m", Urgency.Normal, DISPLAY_SEC)


def test_a_failed_send_neither_raises_nor_stops_later_sends(monkeypatch):
    fake = FakeNotifier(failures=1)
    monkeypatch.setattr(desktop_notifier, "DesktopNotifier", fake)
    notifier = DesktopNotifier("App", Path("app.png"))
    notifier.send("lost", "m", Urgency.Normal, DISPLAY_SEC)
    notifier.send("shown", "m", Urgency.Normal, DISPLAY_SEC)
    assert fake.next_sent()[0] == "shown"
