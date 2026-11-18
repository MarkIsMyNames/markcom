import httpx
import pytest
from nicegui import core, ui
from nicegui.testing import general
from nicegui.testing.user import User

from markcom.page_refresh import keep_current
from markcom.ui_server import configure


class Page:
    """A page over a value something else changes; records each value it draws."""

    def __init__(self):
        self.value = 1
        self.drawn = []
        self.redraws = []

    def build(self):
        @ui.refreshable
        def body(value):
            self.drawn.append(value)
            ui.label(f"value {value}")

        self.redraws.append(keep_current(lambda: self.value, body))


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


async def test_redraws_when_the_value_changed(user, page):
    await user.open("/")
    page.value = 2
    await page.redraws[0]()
    await user.should_see("value 2")
    await user.should_not_see("value 1")


async def test_does_not_redraw_when_nothing_changed(user, page):
    await user.open("/")
    await page.redraws[0]()
    assert page.drawn == [1]
