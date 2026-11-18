"""Redraws a NiceGUI page's body when a change is announced, and only if what it shows changed."""

import logging
from asyncio import AbstractEventLoop
from collections.abc import Awaitable, Callable

from nicegui import Event, core
from nicegui.functions.refreshable import refreshable

logger: logging.Logger = logging.getLogger(__name__)


def announce(changed: Event[[]]) -> None:
    """From any thread: fire `changed` on NiceGUI's event loop, where pages redraw."""
    loop: AbstractEventLoop | None = core.loop
    # None: NiceGUI not started yet, so no page is open to redraw.
    if loop is None:
        logger.debug("change announced before NiceGUI started, so nothing to redraw")
        return
    # Stopped: the app is quitting.
    if not loop.is_running():
        logger.debug("change announced after NiceGUI stopped, so ignored")
        return
    logger.debug("change announced")
    # Event.emit schedules on the loop it is called from, so it must run on NiceGUI's.
    loop.call_soon_threadsafe(changed.emit)


def keep_current[State](
    read: Callable[[], State], body: refreshable[[State], None], changed: Event[[]]
) -> Callable[[], Awaitable[None]]:
    """Draw `body` now, and again each time `changed` fires if the state differs. The returned
    function does the same after the page's own actions."""
    shown: State = read()
    body(shown)
    logger.debug("page drawn")

    async def redraw_if_changed() -> None:
        nonlocal shown
        now: State = read()
        # Same state: a redraw would only close the page's open dialogs.
        if now == shown:
            logger.debug("state unchanged, so no redraw")
            return
        shown = now
        logger.debug("state changed, so redrawing")
        await body.refresh(now)

    # Subscribed from the page, so it ends when the page's client does.
    changed.subscribe(redraw_if_changed)
    return redraw_if_changed
