"""Draws a NiceGUI page's body once and redraws it only when what it shows has changed."""

from collections.abc import Awaitable, Callable

from nicegui import ui
from nicegui.functions.refreshable import refreshable

# Seconds between checks for a change.
REFRESH_SEC: int = 15


def keep_current[State](
    read: Callable[[], State], body: refreshable[[State], None]
) -> Callable[[], Awaitable[None]]:
    """Draw `body` now and on a timer; the returned function redraws it if the state changed."""
    shown: State = read()
    body(shown)

    async def redraw_if_changed() -> None:
        nonlocal shown
        now: State = read()
        if now == shown:
            return
        shown = now
        await body.refresh(now)

    # The first draw is above, so no tick straight away.
    ui.timer(REFRESH_SEC, redraw_if_changed, immediate=False)
    return redraw_if_changed
