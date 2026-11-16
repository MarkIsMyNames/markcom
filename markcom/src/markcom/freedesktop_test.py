import platform
from pathlib import Path

import pytest
from desktop_notifier import Urgency

from markcom import freedesktop
from markcom.freedesktop import (
    DesktopEntryConflictError,
    FreedesktopBackend,
    MissingDesktopEntryError,
    find_desktop_entry,
    install_desktop_entry,
)
from markcom.notifier import NEVER_EXPIRES_SEC, DesktopNotifier


class StubBus:
    """Session bus stand-in: records each Notify call, or raises `failure`."""

    def __init__(self, failure=None):
        self.calls = []
        self._failure = failure

    def notify(self, call):
        if self._failure is not None:
            raise self._failure
        self.calls.append(call)


def install(data_dir, desktop_entry):
    applications = data_dir / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    (applications / f"{desktop_entry}.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")


def sent_with(urgency=Urgency.Normal, display_sec=8, title="t", message="m"):
    bus = StubBus()
    FreedesktopBackend("App", Path("app.png"), "org.example.App", bus).send(
        title, message, urgency, display_sec
    )
    return bus.calls[0]


def test_notification_carries_the_desktop_entry_hint():
    assert sent_with().desktop_entry == "org.example.App"


@pytest.mark.parametrize(("display_sec", "timeout_ms"), [(8, 8000), (NEVER_EXPIRES_SEC, 0)])
def test_display_time_is_sent_in_milliseconds(display_sec, timeout_ms):
    assert sent_with(display_sec=display_sec).timeout_ms == timeout_ms


def test_urgency_is_sent():
    assert sent_with(urgency=Urgency.Critical).urgency is Urgency.Critical


def test_title_and_message_are_sent():
    call = sent_with(title="title", message="body")
    assert (call.title, call.message) == ("title", "body")


def test_installed_entry_is_found_in_any_data_folder(tmp_path):
    install(tmp_path / "system", "org.example.App")
    data_dirs = [tmp_path / "home", tmp_path / "system"]
    assert find_desktop_entry("org.example.App", data_dirs) == "org.example.App"


def test_entry_that_is_not_installed_is_rejected(tmp_path):
    with pytest.raises(MissingDesktopEntryError):
        find_desktop_entry("org.example.Missing", [tmp_path])


def test_installed_entry_names_the_file_it_writes(tmp_path):
    desktop_entry = install_desktop_entry("My App", Path("app.png"), tmp_path)
    desktop_file = tmp_path / "applications" / f"{desktop_entry}.desktop"
    assert "Name=My App" in desktop_file.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize(("app_name", "desktop_entry"), [("My App", "my-app"), ("Café", "cafe")])
def test_installed_entry_is_named_after_the_app(tmp_path, app_name, desktop_entry):
    assert install_desktop_entry(app_name, Path("app.png"), tmp_path) == desktop_entry


def test_another_apps_desktop_file_is_never_overwritten(tmp_path):
    install(tmp_path, "firefox")
    with pytest.raises(DesktopEntryConflictError):
        install_desktop_entry("Firefox", Path("app.png"), tmp_path)
    assert (tmp_path / "applications" / "firefox.desktop").read_text(encoding="utf-8") == (
        "[Desktop Entry]\n"
    )


def test_apps_own_desktop_file_is_kept(tmp_path):
    install_desktop_entry("App", Path("old.png"), tmp_path)
    assert install_desktop_entry("App", Path("new.png"), tmp_path) == "app"


def test_another_markcom_apps_desktop_file_is_never_taken_over(tmp_path):
    install_desktop_entry("My App", Path("app.png"), tmp_path)
    with pytest.raises(DesktopEntryConflictError):
        install_desktop_entry("my app", Path("app.png"), tmp_path)


def test_installing_twice_keeps_one_file(tmp_path):
    install_desktop_entry("App", Path("app.png"), tmp_path)
    install_desktop_entry("App", Path("app.png"), tmp_path)
    assert len(list((tmp_path / "applications").glob("*.desktop"))) == 1


def test_unwritable_data_folder_still_gives_an_entry(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    assert install_desktop_entry("App", Path("app.png"), blocker)


@pytest.fixture
def linux(monkeypatch, tmp_path):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "system"))
    bus = StubBus()
    monkeypatch.setattr(freedesktop, "SessionBus", lambda: bus)
    return bus


def test_notifier_without_an_entry_writes_one_into_the_data_home(linux, tmp_path):
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, 8)
    desktop_entry = linux.calls[0].desktop_entry
    assert (tmp_path / "home" / "applications" / f"{desktop_entry}.desktop").is_file()


def test_notifier_uses_the_apps_own_installed_entry(linux, tmp_path):
    install(tmp_path / "system", "org.example.App")
    DesktopNotifier("App", Path("app.png"), "org.example.App").send("t", "m", Urgency.Normal, 8)
    assert linux.calls[0].desktop_entry == "org.example.App"
    assert not (tmp_path / "home").exists()


@pytest.mark.usefixtures("linux")
def test_notifier_rejects_an_entry_that_is_not_installed():
    with pytest.raises(MissingDesktopEntryError):
        DesktopNotifier("App", Path("app.png"), "org.example.Missing")


@pytest.mark.usefixtures("linux")
def test_failed_linux_send_is_not_raised(monkeypatch):
    monkeypatch.setattr(freedesktop, "SessionBus", lambda: StubBus(OSError("bus gone")))
    DesktopNotifier("App", Path("app.png")).send("t", "m", Urgency.Normal, 8)


@pytest.mark.usefixtures("linux")
def test_linux_programming_errors_are_not_hidden(monkeypatch):
    monkeypatch.setattr(freedesktop, "SessionBus", lambda: StubBus(KeyError("bug")))
    notifier = DesktopNotifier("App", Path("app.png"))
    with pytest.raises(KeyError):
        notifier.send("t", "m", Urgency.Normal, 8)
