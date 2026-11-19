"""markcom's Linux notifications against a fake freedesktop notification service.

Run under a private session bus, never the desktop's own, where the real service holds the
name: `dbus-run-session -- uv run pytest tests/integration --no-cov`.
"""

import asyncio
import multiprocessing
from pathlib import Path

import pytest
from dbus_fast import Message, MessageType, NameFlag, RequestNameReply
from dbus_fast.aio import MessageBus
from desktop_notifier import Urgency

from markcom import freedesktop
from markcom.config import CONFIG
from markcom.notifier import DesktopNotifier

SERVICE = "org.freedesktop.Notifications"
TAKEN = "taken"
READY = "ready"


def accept(message):
    return Message.new_method_return(message, "u", [1])


def reject(message):
    return Message.new_error(message, "org.freedesktop.DBus.Error.Failed", "rejected")


def ignore(_message):
    # True: handled, so the bus sends no reply either
    return True


async def serve(reply, events, stop):
    bus = await MessageBus().connect()
    owner = await bus.request_name(SERVICE, NameFlag.DO_NOT_QUEUE)
    if owner is not RequestNameReply.PRIMARY_OWNER:
        events.put(TAKEN)
        return

    def handle(message):
        if message.message_type is not MessageType.METHOD_CALL or message.member != "Notify":
            return None
        app_name, _, _, title, body, _, hints, timeout_ms = message.body
        plain_hints = {name: variant.value for name, variant in hints.items()}
        events.put((app_name, title, body, plain_hints, timeout_ms))
        return reply(message)

    bus.add_message_handler(handle)
    events.put(READY)
    await asyncio.to_thread(stop.wait)
    bus.disconnect()
    await bus.wait_for_disconnect()


def run_service(reply, events, stop):
    asyncio.run(serve(reply, events, stop))


class FakeNotificationService:
    """Owns org.freedesktop.Notifications in its own process, as a real one does: run as a
    thread of the test process, it never received markcom's blocking call."""

    def __init__(self, reply):
        self._events = multiprocessing.Queue()
        self._stop = multiprocessing.Event()
        self._process = multiprocessing.Process(
            target=run_service, args=(reply, self._events, self._stop)
        )

    def __enter__(self):
        self._process.start()
        if self._events.get(timeout=5) == TAKEN:
            self._process.join(timeout=5)
            taken = f"{SERVICE} is taken: run under dbus-run-session, not the desktop's bus"
            raise RuntimeError(taken)
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._process.join(timeout=5)

    def next_call(self):
        """(app_name, title, body, hints, timeout_ms) of the next Notify call received."""
        return self._events.get(timeout=5)


@pytest.fixture
def data_folders(monkeypatch, tmp_path):
    home = tmp_path / "home"
    system = tmp_path / "system"
    monkeypatch.setenv("XDG_DATA_HOME", str(home))
    monkeypatch.setenv("XDG_DATA_DIRS", str(system))
    return home, system


@pytest.fixture
def service():
    with FakeNotificationService(accept) as running:
        yield running


def hint(call, name):
    _, _, _, hints, _ = call
    return hints[name]


@pytest.mark.usefixtures("data_folders")
def test_notification_arrives_with_its_fields(service):
    DesktopNotifier("Integration App", Path("app.png")).send("title", "body", Urgency.Normal, 3)
    app_name, title, message, _, timeout_ms = service.next_call()
    assert (app_name, title, message, timeout_ms) == ("Integration App", "title", "body", 3000)


@pytest.mark.usefixtures("data_folders")
def test_urgency_arrives(service):
    DesktopNotifier("Integration App", Path("app.png")).send("t", "m", Urgency.Critical, 3)
    assert hint(service.next_call(), "urgency") == 2


def test_app_without_an_entry_names_the_file_markcom_wrote(service, data_folders):
    home, _ = data_folders
    DesktopNotifier("Integration App", Path("app.png")).send("t", "m", Urgency.Normal, 3)
    desktop_entry = hint(service.next_call(), "desktop-entry")
    assert (home / "applications" / f"{desktop_entry}.desktop").is_file()


def test_app_with_an_entry_names_its_own_file(service, data_folders):
    home, system = data_folders
    (system / "applications").mkdir(parents=True)
    (system / "applications" / "org.example.App.desktop").write_text("[Desktop Entry]\n")
    DesktopNotifier("Integration App", Path("app.png"), "org.example.App").send(
        "t", "m", Urgency.Normal, 3
    )
    assert hint(service.next_call(), "desktop-entry") == "org.example.App"
    assert not home.exists()


@pytest.mark.usefixtures("data_folders")
def test_rejected_notification_is_not_raised():
    with FakeNotificationService(reject) as service:
        DesktopNotifier("Integration App", Path("app.png")).send("t", "m", Urgency.Normal, 3)
    assert service.next_call()


@pytest.mark.usefixtures("data_folders")
def test_unanswered_notification_times_out(monkeypatch):
    short = CONFIG.model_copy(update={"notification_reply_timeout_sec": 0.5})
    monkeypatch.setattr(freedesktop, "CONFIG", short)
    with FakeNotificationService(ignore) as service:
        DesktopNotifier("Integration App", Path("app.png")).send("t", "m", Urgency.Normal, 3)
    assert service.next_call()


@pytest.mark.usefixtures("data_folders")
def test_missing_session_bus_is_not_raised(monkeypatch):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS")
    DesktopNotifier("Integration App", Path("app.png")).send("t", "m", Urgency.Normal, 3)
