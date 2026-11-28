import asyncio
import queue
import threading
from pathlib import Path

import pytest
from dbus_fast import Message, MessageType

from markcom import notifier
from markcom.notifier import NEVER_EXPIRES_SEC, FreedesktopNotifier, Urgency

DISPLAY_SEC = 8
WAIT_SEC = 5
DESKTOP_ENTRY = "org.example.App"


class FakeBus:
    """Queues each Notify; fails the first `failures` calls; replies `reply`."""

    def __init__(self, failures=0, reply=None):
        self.sent = queue.Queue()
        self._failures = failures
        self._reply = reply

    def __call__(self):
        return self

    async def connect(self):
        return self

    async def call(self, message):
        await asyncio.sleep(0)
        if self._failures:
            self._failures -= 1
            bug = "bug"
            raise KeyError(bug)
        self.sent.put(message)
        return self._reply

    def next_sent(self):
        return self.sent.get(timeout=WAIT_SEC)


@pytest.fixture
def bus(monkeypatch):
    fake = FakeBus()
    monkeypatch.setattr(notifier, "MessageBus", fake)
    return fake


def make_notifier():
    return FreedesktopNotifier("App", Path("app.png"), DESKTOP_ENTRY)


def fields(message):
    app_name, _, icon, title, body, _, hints, timeout_ms = message.body
    return app_name, icon, title, body, hints["urgency"].value, timeout_ms


def test_send_shows_it_for_the_display_time_given(bus):
    make_notifier().send("t", "m", Urgency.Normal, DISPLAY_SEC)
    assert fields(bus.next_sent()) == (
        "App",
        Path("app.png").resolve().as_uri(),
        "t",
        "m",
        Urgency.Normal.value,
        DISPLAY_SEC * 1000,
    )


def test_never_expires_sec_keeps_the_notification_until_dismissed(bus):
    make_notifier().send("t", "m", Urgency.Critical, NEVER_EXPIRES_SEC)
    assert fields(bus.next_sent())[4:] == (Urgency.Critical.value, NEVER_EXPIRES_SEC)


def test_each_send_names_the_apps_desktop_entry(bus):
    make_notifier().send("t", "m", Urgency.Normal, DISPLAY_SEC)
    assert bus.next_sent().body[6]["desktop-entry"].value == DESKTOP_ENTRY


def test_sends_from_two_threads_at_once_both_arrive(bus):
    sender = make_notifier()
    senders = [
        threading.Thread(target=sender.send, args=(title, "m", Urgency.Normal, DISPLAY_SEC))
        for title in ("a", "b")
    ]
    for thread in senders:
        thread.start()
    for thread in senders:
        thread.join()
    assert sorted(fields(bus.next_sent())[2] for _ in senders) == ["a", "b"]


async def test_a_send_from_inside_a_running_event_loop_arrives(bus):
    make_notifier().send("t", "m", Urgency.Normal, DISPLAY_SEC)
    assert fields(await asyncio.to_thread(bus.next_sent))[2] == "t"


def test_a_failed_send_does_not_stop_later_sends(monkeypatch):
    fake = FakeBus(failures=1)
    monkeypatch.setattr(notifier, "MessageBus", fake)
    sender = make_notifier()
    sender.send("lost", "m", Urgency.Normal, DISPLAY_SEC)
    sender.send("shown", "m", Urgency.Normal, DISPLAY_SEC)
    assert fields(fake.next_sent())[2] == "shown"


def test_a_refused_send_does_not_stop_later_sends(monkeypatch):
    refused = Message(message_type=MessageType.ERROR, error_name="x.Error", reply_serial=1)
    fake = FakeBus(reply=refused)
    monkeypatch.setattr(notifier, "MessageBus", fake)
    sender = make_notifier()
    for title in ("first", "second"):
        sender.send(title, "m", Urgency.Normal, DISPLAY_SEC)
    assert [fields(fake.next_sent())[2] for _ in range(2)] == ["first", "second"]
