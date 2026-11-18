import asyncio
from contextlib import closing

import httpx
import pytest
from nicegui import Event, core, ui
from nicegui.testing import general
from nicegui.testing.user import User

from markcom.page_refresh import announce, keep_current
from markcom.ui_server import configure


class Page:
    """A page over a value something else changes; records each value it draws."""

    def __init__(self):
        self.value = 1
        self.drawn = []
        self.changed = Event()
        self.redraws = []

    def build(self):
        @ui.refreshable
        def body(value):
            self.drawn.append(value)
            ui.label(f"value {value}")

        self.redraws.append(keep_current(lambda: self.value, body, self.changed))


@pytest.fixture
def page():
    return Page()


@pytest.fixture
async def user(page, monkeypatch):
    """A person at the page in a browser, simulated by NiceGUI."""
    monkeypatch.setenv("NICEGUI_USER_SIMULATION", "true")
    # User swaps in its own notify and navigate; put NiceGUI's back after.
    monkeypatch.setattr(ui, "notify", ui.notify)
    monkeypatch.setattr(ui, "navigate", ui.navigate)
    with general.nicegui_reset_globals():
        configure(page.build, "App")
        async with (
            core.app.router.lifespan_context(core.app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(core.app), base_url="http://127.0.0.1:8765"
            ) as client,
        ):
            yield User(client)


async def test_draws_the_current_value_when_the_page_opens(user):
    await user.open("/")
    await user.should_see("value 1")


async def test_a_change_announced_from_another_thread_redraws_the_page(user, page):
    await user.open("/")
    page.value = 2
    await asyncio.to_thread(announce, page.changed)
    await user.should_see("value 2")
    await user.should_not_see("value 1")


async def test_an_announcement_with_nothing_changed_does_not_redraw(user, page):
    await user.open("/")
    await page.changed.call()
    assert page.drawn == [1]


async def test_the_returned_function_redraws_after_the_pages_own_action(user, page):
    await user.open("/")
    page.value = 2
    await page.redraws[0]()
    await user.should_see("value 2")


def heard_after_announcing():
    heard = []
    changed = Event()
    changed.subscribe(lambda: heard.append(True))
    announce(changed)
    return heard


def test_an_announcement_before_nicegui_starts_reaches_no_one(monkeypatch):
    monkeypatch.setattr(core, "loop", None)
    assert heard_after_announcing() == []


def test_an_announcement_after_nicegui_stops_reaches_no_one(monkeypatch):
    with closing(asyncio.new_event_loop()) as stopped:
        monkeypatch.setattr(core, "loop", stopped)
        assert heard_after_announcing() == []


class ClosingLoop:
    """NiceGUI's loop closing between announce's check and its call, as it can while quitting."""

    def is_running(self):
        return True

    def call_soon_threadsafe(self, *_):
        closed = "Event loop is closed"
        raise RuntimeError(closed)


def test_an_announcement_as_nicegui_closes_reaches_no_one(monkeypatch):
    monkeypatch.setattr(core, "loop", ClosingLoop())
    assert heard_after_announcing() == []
