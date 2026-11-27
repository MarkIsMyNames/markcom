"""markcom's Linux notifications against a fake freedesktop notification service.

Run under a private session bus, never the desktop's own, where the real service holds the
name: `dbus-run-session -- uv run pytest tests/integration --no-cov`.
"""

import asyncio
import multiprocessing
from pathlib import Path
from typing import Annotated

import pytest
from dbus_fast import NameFlag, RequestNameReply
from dbus_fast.aio import MessageBus
from dbus_fast.annotations import DBusDict, DBusInt32, DBusSignature, DBusStr, DBusUInt32
from dbus_fast.service import ServiceInterface, dbus_method
from desktop_notifier import Urgency

from markcom.notifier import DesktopNotifier

SERVICE = "org.freedesktop.Notifications"
SERVICE_PATH = "/org/freedesktop/Notifications"
# Notify replies with the new notification's ID, never 0.
NOTIFICATION_ID = 1
# freedesktop Notifications spec: urgency hint byte for critical.
CRITICAL_URGENCY_BYTE = 2
MS_PER_SEC = 1000
DISPLAY_SEC = 3
WAIT_SEC = 5
TAKEN = "taken"
READY = "ready"


class Notifications(ServiceInterface):
    """Records each Notify call; desktop-notifier introspects it first, so it must be a real
    interface rather than a bare message handler."""

    def __init__(self, events):
        super().__init__(SERVICE)
        self._events = events

    @dbus_method(name="Notify")
    def notify(
        self,
        app_name: DBusStr,
        _replaces_id: DBusUInt32,
        _app_icon: DBusStr,
        summary: DBusStr,
        body: DBusStr,
        _actions: Annotated[list[str], DBusSignature("as")],
        hints: DBusDict,
        expire_timeout: DBusInt32,
    ) -> DBusUInt32:
        plain_hints = {name: variant.value for name, variant in hints.items()}
        self._events.put((app_name, summary, body, plain_hints, expire_timeout))
        return NOTIFICATION_ID

    @dbus_method(name="GetCapabilities")
    def get_capabilities(self) -> Annotated[list[str], DBusSignature("as")]:
        return ["body"]

    @dbus_method(name="GetServerInformation")
    def get_server_information(
        self,
    ) -> Annotated[tuple[str, str, str, str], DBusSignature("ssss")]:
        return ("Fake", "markcom", "1", "1.2")


async def serve(events, stop):
    bus = await MessageBus().connect()
    bus.export(SERVICE_PATH, Notifications(events))
    owner = await bus.request_name(SERVICE, NameFlag.DO_NOT_QUEUE)
    if owner is not RequestNameReply.PRIMARY_OWNER:
        events.put(TAKEN)
        return
    events.put(READY)
    await asyncio.to_thread(stop.wait)
    bus.disconnect()
    await bus.wait_for_disconnect()


def run_service(events, stop):
    asyncio.run(serve(events, stop))


class FakeNotificationService:
    """Owns org.freedesktop.Notifications in its own process, as a real one does: run as a
    thread of the test process, it never received markcom's blocking call."""

    def __init__(self):
        self._events = multiprocessing.Queue()
        self._stop = multiprocessing.Event()
        self._process = multiprocessing.Process(target=run_service, args=(self._events, self._stop))

    def __enter__(self):
        self._process.start()
        if self._events.get(timeout=WAIT_SEC) == TAKEN:
            self._process.join(timeout=WAIT_SEC)
            taken = f"{SERVICE} is taken: run under dbus-run-session, not the desktop's bus"
            raise RuntimeError(taken)
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._process.join(timeout=WAIT_SEC)

    def next_call(self):
        """(app_name, title, body, hints, timeout_ms) of the next Notify call received."""
        return self._events.get(timeout=WAIT_SEC)


@pytest.fixture
def service():
    with FakeNotificationService() as running:
        yield running


def test_notification_arrives_with_its_fields(service):
    DesktopNotifier("Integration App", Path("app.png")).send(
        "title", "body", Urgency.Normal, DISPLAY_SEC
    )
    app_name, title, message, _, timeout_ms = service.next_call()
    assert (app_name, title, message, timeout_ms) == (
        "Integration App",
        "title",
        "body",
        DISPLAY_SEC * MS_PER_SEC,
    )


def test_urgency_arrives(service):
    DesktopNotifier("Integration App", Path("app.png")).send(
        "t", "m", Urgency.Critical, DISPLAY_SEC
    )
    _, _, _, hints, _ = service.next_call()
    assert hints["urgency"] == CRITICAL_URGENCY_BYTE


async def test_notification_sent_from_inside_an_event_loop_arrives(service):
    DesktopNotifier("Integration App", Path("app.png")).send("t", "m", Urgency.Normal, DISPLAY_SEC)
    assert service.next_call()
